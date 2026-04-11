from fastapi import FastAPI, Depends, HTTPException, Request, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import json
import os
import shutil
import io
from scripts import word_parser

from . import models, crud, database
from .services import get_all_transcripts, tokenize_chinese, generate_wordcloud_image, get_word_frequencies, invalidate_cache

# Create tables
models.Base.metadata.create_all(bind=database.engine)


def ensure_image_column():
    # Backfill schema for existing SQLite DBs created before `image` was added.
    with database.engine.begin() as conn:
        columns = conn.execute(text("PRAGMA table_info(inscriptions)"))
        column_names = {row[1] for row in columns}
        if "image" not in column_names:
            conn.execute(text("ALTER TABLE inscriptions ADD COLUMN image TEXT"))


ensure_image_column()

app = FastAPI(title="Inscription Retrieval System")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/preview", response_class=HTMLResponse)
async def preview_new_design(request: Request):
    """临时预览新古典风格页面"""
    return templates.TemplateResponse("index_new.html", {"request": request})


@app.get("/api/search")
def search(
    q: str,
    fields: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * size
    limit = size
    results, total_count = crud.search_inscriptions(db, q, fields=fields, skip=skip, limit=limit)
    # Parse image_url JSON string back to list for response
    for item in results:
        if item.image_url:
            try:
                item.image_url = json.loads(item.image_url)
            except:
                item.image_url = []
    
    return {
        "items": results,
        "total": total_count,
        "page": page,
        "size": size
    }


@app.get("/api/inscriptions/{inscription_id}")
def read_inscription(inscription_id: int, db: Session = Depends(get_db)):
    db_inscription = crud.get_inscription(db, inscription_id=inscription_id)
    if db_inscription is None:
        raise HTTPException(status_code=404, detail="Inscription not found")

    # Parse image_url
    if db_inscription.image_url:
        try:
            db_inscription.image_url = json.loads(db_inscription.image_url)
        except:
            db_inscription.image_url = []

    return db_inscription


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.post("/api/inscriptions/overwrite")
def overwrite_inscription(data: dict, db: Session = Depends(get_db)):
    """
    Overwrite an existing inscription with new data.
    Input: { "existing_id": int, "new_data": dict }
    """
    existing_id = data.get("existing_id")
    new_data = data.get("new_data")

    if not existing_id or not new_data:
        raise HTTPException(status_code=400, detail="Missing existing_id or new_data")

    db_obj = crud.get_inscription(db, existing_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Inscription not found")

    # Update fields
    for key, value in new_data.items():
        if hasattr(db_obj, key):
            setattr(db_obj, key, value)

    db.commit()
    db.refresh(db_obj)

    # 数据更新后清除缓存
    invalidate_cache()

    return {"status": "success", "id": db_obj.id, "name": db_obj.name}


@app.delete("/api/inscriptions/{inscription_id}")
def delete_inscription(inscription_id: int, db: Session = Depends(get_db)):
    db_obj = crud.get_inscription(db, inscription_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Inscription not found")

    # Optional: Delete associated images if needed (not implemented here to be safe)

    db.delete(db_obj)
    db.commit()

    # 数据删除后清除缓存
    invalidate_cache()

    return {"status": "success", "message": f"Inscription {inscription_id} deleted"}


@app.get("/api/wordcloud")
def get_wordcloud(
    era: Optional[str] = Query(None, description="Filter by era (时代)"),
    width: int = Query(1200, description="Image width in pixels"),
    height: int = Query(800, description="Image height in pixels"),
    max_words: int = Query(200, description="Maximum number of words"),
    db: Session = Depends(get_db),
):
    """
    Generate a word cloud image from inscription transcripts.

    - **era**: Optional era filter (e.g., "唐代", "宋代")
    - **width**: Image width (default 1200)
    - **height**: Image height (default 800)
    - **max_words**: Maximum words to display (default 200)

    Returns a PNG image.
    """
    transcripts = get_all_transcripts(db, era=era)

    if not transcripts or not transcripts.strip():
        from .services.wordcloud_service import _generate_empty_image
        img_bytes = _generate_empty_image(width, height)
    else:
        tokenized_text = tokenize_chinese(transcripts)
        img_bytes = generate_wordcloud_image(
            tokenized_text,
            width=width,
            height=height,
            max_words=max_words,
        )

    return StreamingResponse(
        io.BytesIO(img_bytes),
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=wordcloud.png"},
    )


@app.get("/api/frequencies")
def get_word_frequencies_endpoint(
    era: Optional[str] = Query(None, description="Filter by era (时代)"),
    top_n: int = Query(50, description="Number of top words to return"),
    db: Session = Depends(get_db),
):
    """
    Get word frequency statistics from inscription transcripts.

    - **era**: Optional era filter (e.g., "唐代", "宋代")
    - **top_n**: Number of top words to return (default 50)

    Returns JSON with word frequencies.
    """
    transcripts = get_all_transcripts(db, era=era)
    frequencies = get_word_frequencies(transcripts, top_n=top_n)
    return {"frequencies": [{"word": word, "count": count} for word, count in frequencies]}


@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...), db: Session = Depends(get_db)
):
    """
    Upload multiple Word files, parse them, and import inscriptions.
    """
    total_success = 0
    total_skipped = 0
    all_skipped_items = []
    errors = []

    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)

    for file in files:
        if not file.filename.endswith((".docx", ".doc")):
            errors.append(f"Skipped {file.filename}: Not a Word file")
            continue

        temp_path = os.path.join(temp_dir, file.filename)
        try:
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Process import
            result = word_parser.process_import(temp_path, db)

            total_success += result.get("success", 0)
            total_skipped += result.get("skipped", 0)
            if result.get("skipped_items"):
                # Add filename source to skipped items for clarity
                for item in result["skipped_items"]:
                    item["source_file"] = file.filename
                all_skipped_items.extend(result["skipped_items"])

            if result.get("errors"):
                errors.extend([f"{file.filename}: {e}" for e in result["errors"]])

        except Exception as e:
            import traceback

            traceback.print_exc()
            errors.append(f"Error processing {file.filename}: {str(e)}")

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # 数据更新后清除缓存
    if total_success > 0:
        invalidate_cache()

    return {
        "success": total_success,
        "skipped": total_skipped,
        "skipped_items": all_skipped_items,
        "errors": errors,
    }
