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
from .services import (
    get_all_transcripts,
    tokenize_chinese,
    generate_wordcloud_image,
    get_word_frequencies,
    get_official_titles_text,
    get_official_titles_set,
)

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


# Middleware to disable browser cache
@app.middleware("http")
async def disable_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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


@app.get("/full_transcript", response_class=HTMLResponse)
async def full_transcript(request: Request):
    """志文全屏展示页面"""
    return templates.TemplateResponse("full_transcript.html", {"request": request})


@app.get("/api/search")
def search(
    q: str,
    fields: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(15, ge=1, le=100),
    sort_by: Optional[str] = Query(None, description="Sort field: id, name, era, serial_num"),
    sort_order: Optional[str] = Query("asc", description="Sort order: asc or desc"),
    db: Session = Depends(get_db),
):
    skip = (page - 1) * size
    limit = size
    results, total_count = crud.search_inscriptions(
        db, q, fields=fields, skip=skip, limit=limit,
        sort_by=sort_by, sort_order=sort_order
    )
    # Parse image_url JSON string back to list for response
    for item in results:
        if item.image_url:
            try:
                item.image_url = json.loads(item.image_url)
            except:
                item.image_url = []

    return {"items": results, "total": total_count, "page": page, "size": size}


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
    Input: { "existing_id": int, "new_data": dict } or { "existing_id": int, "conflict_token": str }
    """
    existing_id = data.get("existing_id")
    new_data = data.get("new_data")
    conflict_token = data.get("conflict_token")

    if not new_data and conflict_token:
        new_data = word_parser.load_conflict_record(conflict_token)

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
    if conflict_token:
        word_parser.delete_conflict_record(conflict_token)

    return {"status": "success", "id": db_obj.id, "name": db_obj.name}


@app.patch("/api/inscriptions/{inscription_id}")
def update_inscription(
    inscription_id: int,
    data: dict,
    db: Session = Depends(get_db)
):
    """部分更新单条记录"""
    db_obj = crud.get_inscription(db, inscription_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Inscription not found")

    # 字段白名单
    ALLOWED_FIELDS = {
        "serial_num", "name", "era", "alias", "discovery",
        "collection", "publication", "format", "image", "transcript", "image_url"
    }
    updates = {k: v for k, v in data.items() if k in ALLOWED_FIELDS}
    updated = crud.update_inscription(db, inscription_id, updates)
    return updated


@app.delete("/api/inscriptions/batch-delete")
def batch_delete_inscriptions(data: dict, db: Session = Depends(get_db)):
    inscription_ids = data.get("ids")
    if not isinstance(inscription_ids, list) or not inscription_ids:
        raise HTTPException(status_code=400, detail="ids must be a non-empty list")

    valid_ids = []
    invalid_ids = []
    for item in inscription_ids:
        try:
            valid_ids.append(int(item))
        except (TypeError, ValueError):
            invalid_ids.append(item)

    if not valid_ids:
        raise HTTPException(status_code=400, detail="ids must contain valid integers")

    unique_ids = sorted(set(valid_ids))
    db_objs = (
        db.query(models.Inscription)
        .filter(models.Inscription.id.in_(unique_ids))
        .all()
    )
    found_ids = {item.id for item in db_objs}
    not_found_ids = [item_id for item_id in unique_ids if item_id not in found_ids]

    for db_obj in db_objs:
        db.delete(db_obj)
    db.commit()

    return {
        "status": "success",
        "deleted": len(db_objs),
        "deleted_ids": sorted(found_ids),
        "not_found_ids": not_found_ids,
        "invalid_ids": invalid_ids,
    }


@app.delete("/api/inscriptions/{inscription_id}")
def delete_inscription(inscription_id: int, db: Session = Depends(get_db)):
    db_obj = crud.get_inscription(db, inscription_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Inscription not found")

    # Optional: Delete associated images if needed (not implemented here to be safe)

    db.delete(db_obj)
    db.commit()

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
    return {
        "frequencies": [{"word": word, "count": count} for word, count in frequencies]
    }


@app.get("/api/timeline")
def get_timeline(
    page: int = 1,
    page_size: int = 50,
    include_all: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get inscriptions grouped by era for timeline visualization.
    Returns eras sorted by historical order with count and sample inscriptions.

    Query params:
    - page: Page number (1-indexed, default 1)
    - page_size: Number of eras per page (default 50, set higher for more eras)
    - include_all: If true, return all inscriptions for each era (not just 5 samples)
    """
    result = crud.get_timeline_data(db, page=page, page_size=page_size, include_all=include_all)
    return result



@app.get("/api/inscriptions/by-era/{era_name}")
def get_inscriptions_by_era(era_name: str, db: Session = Depends(get_db)):
    """按年号名称筛选墓志"""
    inscriptions = crud.get_inscriptions_by_era(db, era_name)
    # Parse image_url JSON string back to list
    for item in inscriptions:
        if item.image_url:
            try:
                item.image_url = json.loads(item.image_url)
            except:
                item.image_url = []
    return {"items": inscriptions, "total": len(inscriptions)}


@app.get("/api/frequencies/official-titles")
def get_official_titles_frequencies(
    era: Optional[str] = Query(None, description="Filter by era (时代)"),
    top_n: int = Query(50, description="Number of top words to return"),
    type: Optional[str] = Query("south", description="Type of officials: 'south' or 'north'"),
    db: Session = Depends(get_db),
):
    """
    Get word frequency statistics from inscription transcripts for specified official titles.

    - **era**: Optional era filter (e.g., "唐代", "宋代")
    - **top_n**: Number of top words to return (default 50)
    - **type**: 'south' for 南面官, 'north' for 北面官

    Returns JSON with word frequencies.
    """
    import re

    # 南面官官称列表（简体 + 繁体版本）
    SOUTH_OFFICIAL_TITLE_PAIRS = [
        ("處置使", ["处置使", "處置使"]),
        ("制置使", ["制置使"]),
        ("兵馬都總管", ["兵马都总管", "兵馬都總管"]),
        ("點檢", ["点检", "點檢"]),
        ("轉運使", ["转运使", "轉運使"]),
        ("節度使", ["节度使", "節度使"]),
        ("節度副使", ["节度副使", "節度副使"]),
        ("行軍司馬", ["行军司马", "行軍司馬"]),
        ("團練使", ["团练使", "團練習"]),
        ("觀察使", ["观察使", "觀察使"]),
        ("觀察判官", ["观察判官", "觀察判官"]),
        ("商稅判官", ["商税判官"]),
        ("軍事判官", ["军事判官", "軍事判官"]),
        ("留守判官", ["留守判官"]),
        ("防禦使", ["防御使", "防禦使"]),
        ("州刺史", ["州刺史"]),
        ("州軍州事", ["州军州事"]),
        ("縣令", ["县令", "縣令"]),
        ("縣丞", ["县丞", "縣丞"]),
        ("縣主簿", ["县主簿", "縣主簿"]),
        ("縣尉", ["县尉", "縣尉"]),
        ("留守事", ["留守事"]),
        ("都總管", ["都总管", "都總管"]),
        ("都虞候", ["都虞候"]),
        ("警巡", ["警巡"]),
        ("博士", ["博士"]),
        ("都部署", ["都部署"]),
        ("檢校太子賓客", ["检校太子宾客", "檢校太子賓客", "太子賓客"]),
        ("太子太傅", ["太子太傅"]),
        ("太子少傅", ["太子少傅"]),
        ("太子太師", ["太子太师", "太子太師"]),
        ("太子太保", ["太子太保"]),
        ("太子少保", ["太子少保"]),
        ("太子洗馬", ["太子洗马", "太子洗馬"]),
        ("太子中舍", ["太子中舍"]),
        ("太子中允", ["太子中允"]),
        ("校書郎", ["校书郎", "校書郎"]),
        ("秘書監", ["秘书监", "秘書監", "秘書少監"]),
        ("開國子", ["开国子", "開國子"]),
        ("檢校國子祭酒", ["检校国子祭酒", "檢校國子祭酒", "國子祭酒"]),
        ("太僕卿", ["太仆卿", "太僕卿", "太僕少卿"]),
        ("大理寺", ["大理寺"]),
        ("司農卿", ["司农少卿", "司農卿"]),
        ("宣政殿學士", ["宣政殿学士", "宣政殿學士", "宣政殿大學士"]),
        ("觀書殿學士", ["观书殿学士", "觀書殿學士"]),
        ("昭文館直學士", ["昭文馆直学士", "昭文館直學士"]),
        ("乾文閣待制", ["乾文阁待制", "乾文閣待制", "乾文閣待制直學士"]),
        ("翰林學士", ["翰林学士", "翰林學士"]),
        ("宣徽使", ["宣徽使"]),
        ("知内承宣事", ["知内承宣事", "知承宣事"]),
        ("尚書令", ["尚书令", "尚書令"]),
        ("左僕射", ["左仆射", "左僕射"]),
        ("右僕射", ["右仆射", "右僕射"]),
        ("参知政事", ["参知政事", "參知政事"]),
        ("禮部尚書", ["礼部尚书", "禮部尚書"]),
        ("吏部尚書", ["吏部尚书", "吏部尚書"]),
        ("兵部尚書", ["兵部尚书", "兵部尚書"]),
        ("刑部尚書", ["刑部尚书", "刑部尚書"]),
        ("工部尚書", ["工部尚书", "工部尚書"]),
        ("監察御史", ["监察御史", "監察御史"]),
        ("御史大夫", ["御史大夫"]),
        ("御史中丞", ["御史中丞"]),
        ("殿中侍御史", ["殿中侍御史"]),
        ("殿中丞", ["殿中丞"]),
        ("殿中監", ["殿中监", "殿中監", "殿中少監"]),
        ("檢校太師", ["检校太师", "檢校太師"]),
        ("檢校太保", ["检校太保", "檢校太保"]),
        ("檢校太傅", ["检校太傅", "檢校太傅"]),
        ("檢校太尉", ["检校太尉", "檢校太尉"]),
        ("檢校司徒", ["检校司徒", "檢校司徒"]),
        ("檢校司空", ["检校司空", "檢校司空"]),
        ("中書令", ["中书令", "中書令"]),
        ("大丞相", ["大丞相"]),
        ("左丞相", ["左丞相"]),
        ("中書侍郎", ["中书侍郎", "中書侍郎"]),
        ("中書省事", ["中书省事", "中書省事"]),
        ("中書門下平章事", ["中书门下平章事", "中書門下平章事"]),
        ("門下侍郎", ["门下侍郎", "門下侍郎"]),
        ("崇禄大夫", ["崇禄大夫"]),
    ]

    # 北面官官称列表（简体 + 繁体版本）
    NORTH_OFFICIAL_TITLE_PAIRS = [
        ("糺使", ["糺使"]),
        ("惕隱", ["惕隐", "惕隱"]),
        ("夷離畢", ["夷离毕", "夷離畢"]),
        ("林牙", ["林牙"]),
        ("侍衛", ["侍卫", "侍衛"]),
        ("宣徽南院", ["宣徽南院", "南院宣徽", "南院"]),
        ("宣徽北院", ["宣徽北院", "北院宣徽", "北院"]),
        ("都統軍", ["都统军", "都統軍"]),
        ("南大王", ["南大王"]),
        ("北大王", ["北大王"]),
        ("北樞密院", ["北枢密院", "北樞密院"]),
        ("樞密使", ["枢密使", "樞密使"]),
        ("北宰相", ["北宰相"]),
        ("南宰相", ["南宰相"]),
        ("于越", ["于越"]),
        ("警巡", ["警巡"]),
        ("詳穩", ["详稳", "詳穩"]),
    ]

    # 选择南面官或北面官
    title_pairs = SOUTH_OFFICIAL_TITLE_PAIRS if type == "south" else NORTH_OFFICIAL_TITLE_PAIRS

    # 获取碑文文本
    transcripts = get_all_transcripts(db, era=era)
    if not transcripts:
        return {"frequencies": []}

    # 清理文本
    text = re.sub(r"<[^>]+>", "", transcripts)
    text = re.sub(r"\s+", " ", text)

    # 统计词语出现次数
    title_counts = {}
    for display_name, variants in title_pairs:
        total_count = sum(len(re.findall(re.escape(v), text)) for v in variants)
        if total_count > 0:
            title_counts[display_name] = total_count

    # 按出现次数排序
    frequencies = sorted(title_counts.items(), key=lambda x: -x[1])[:top_n]
    return {
        "frequencies": [{"word": word, "count": count} for word, count in frequencies]
    }


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
