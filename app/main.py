from fastapi import FastAPI, Depends, HTTPException, Request, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import json
import os
import shutil
from scripts import word_parser

from . import models, crud, database

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


@app.get("/api/search")
def search(
    q: str, fields: Optional[List[str]] = Query(None), db: Session = Depends(get_db)
):
    results = crud.search_inscriptions(db, q, fields=fields)
    # Parse image_url JSON string back to list for response
    for item in results:
        if item.image_url:
            try:
                item.image_url = json.loads(item.image_url)
            except:
                item.image_url = []
    return results


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
    return {"status": "success", "id": db_obj.id, "name": db_obj.name}


@app.delete("/api/inscriptions/{inscription_id}")
def delete_inscription(inscription_id: int, db: Session = Depends(get_db)):
    db_obj = crud.get_inscription(db, inscription_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Inscription not found")

    # Optional: Delete associated images if needed (not implemented here to be safe)

    db.delete(db_obj)
    db.commit()
    return {"status": "success", "message": f"Inscription {inscription_id} deleted"}


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

    return {
        "success": total_success,
        "skipped": total_skipped,
        "skipped_items": all_skipped_items,
        "errors": errors,
    }
