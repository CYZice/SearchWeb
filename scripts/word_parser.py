import os
import re
import json
import sys
import hashlib
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from sqlalchemy.orm import Session

# Add root to path
sys.path.append(os.getcwd())

from app.models import Base, Inscription
from app.database import engine, SessionLocal

# Constants
RAW_DOCS_DIR = "data/raw_word"
IMAGES_DIR = "app/static/images"
CHAR_IMAGES_DIR = "app/static/images/chars"
# Ensure we use the correct path separator for URLs (forward slash)
IMAGE_URL_PREFIX = "/static/images/"
CHAR_IMAGE_URL_PREFIX = "/static/images/chars/"

# Ensure char directory exists
os.makedirs(CHAR_IMAGES_DIR, exist_ok=True)

# Field Mapping
FIELD_MAP = {
    "器名": "name",
    "时代": "era",
    "時代": "era",
    "别称": "alias",
    "別稱": "alias",
    "出土": "discovery",
    "发现": "discovery",
    "發現": "discovery",
    "现藏": "collection",
    "現藏": "collection",
    "著录": "publication",
    "著錄": "publication",
    "形制": "format",
    "图片": "image",
    "圖片": "image",
    "释文": "transcript",
    "釋文": "transcript",
    "誌文": "transcript",
}


def setup_database():
    print("Recreating database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def get_images_from_run(run, doc):
    """
    Extract image parts from a run.
    """
    images = []

    # Namespaces usually used in docx xml
    nsmap = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    }

    if run.element is None:
        return images

    # Find drawing elements
    # Note: python-docx elements usually have nsmap
    drawings = run.element.findall(".//w:drawing", run.element.nsmap)

    for drawing in drawings:
        # Find blip
        blips = drawing.findall(".//a:blip", nsmap)
        for blip in blips:
            embed_id = blip.get(f"{{{nsmap['r']}}}embed")
            if embed_id:
                try:
                    part = doc.part.related_parts[embed_id]
                    images.append(part)
                except KeyError:
                    pass
    return images


def save_image(image_part, serial_num, index):
    """
    Save image part to disk and return relative URL.
    """
    # Determine extension
    content_type = image_part.content_type
    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "jpeg" in content_type:
        ext = "jpg"

    # Clean serial num for filename (remove brackets)
    clean_serial = re.sub(r"[^\w]", "", serial_num)
    if not clean_serial:
        clean_serial = "unknown"

    filename = f"{clean_serial}_{index}.{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(image_part.blob)

    return f"{IMAGE_URL_PREFIX}{filename}"


def save_char_image(image_part):
    """
    Save small character image based on content hash to avoid duplicates.
    """
    content = image_part.blob
    # Calculate MD5 hash
    md5_hash = hashlib.md5(content).hexdigest()

    # Determine extension
    content_type = image_part.content_type
    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "jpeg" in content_type:
        ext = "jpg"

    filename = f"{md5_hash}.{ext}"
    filepath = os.path.join(CHAR_IMAGES_DIR, filename)

    # Only write if doesn't exist
    if not os.path.exists(filepath):
        with open(filepath, "wb") as f:
            f.write(content)

    return f"{CHAR_IMAGE_URL_PREFIX}{filename}"


def parse_docx(file_path):
    """
    Parse a Word document and return a list of inscription dictionaries.
    Does NOT save to database.
    """
    doc = Document(file_path)

    records = []
    current_record = None
    current_field = None
    image_counter = 1

    # Regex for new record: 【017】 or [017]
    record_pattern = re.compile(r"^[【\[](\d+)[】\]]")

    # Regex for field: Key: Value (restrict key length to avoid matching long texts with colons)
    field_pattern = re.compile(r"^([^，。；：！？\s：:]{1,10})[\s]*[：:](.*)")

    def finalize_record():
        nonlocal current_record
        if current_record:
            # Convert image_list to JSON string
            if "image_list" in current_record:
                current_record["image_url"] = json.dumps(current_record["image_list"])
                del current_record["image_list"]

            records.append(current_record)
            current_record = None

    for para in doc.paragraphs:
        # Get raw text for pattern matching
        raw_text = para.text.strip()

        # 1. Check for New Record Start
        match = record_pattern.match(raw_text)
        if match:
            finalize_record()

            serial_num_str = match.group(0)  # e.g., 【017】

            current_record = {"serial_num": serial_num_str, "image_list": []}
            image_counter = 1
            current_field = None
            continue

        # If we are not in a record yet, skip (or handle preamble)
        if current_record is None:
            continue

        # 2. Process Content (Text + Images)
        para_html_content = ""

        for run in para.runs:
            # Append run text
            if run.text:
                para_html_content += run.text

            # Check for images in this run
            images = get_images_from_run(run, doc)
            for img_part in images:
                # Check size: If < 50KB (51200 bytes), treat as char image
                if len(img_part.blob) < 51200:
                    url = save_char_image(img_part)
                    # Insert img tag inline
                    para_html_content += f'<img src="{url}" class="inline-char" style="height: 1.2em; vertical-align: middle;" />'
                else:
                    # Treat as inscription image
                    url = save_image(
                        img_part, current_record["serial_num"], image_counter
                    )
                    current_record["image_list"].append(url)
                    image_counter += 1

        # 3. Parse Fields
        if not raw_text and not para_html_content:
            continue

        field_match = field_pattern.match(raw_text)
        if field_match:
            key_raw = field_match.group(1).strip()

            # Find mapped key
            db_key = None
            # Normalize key_raw (remove punctuation just in case)
            key_clean = re.sub(r"[^\w\u4e00-\u9fa5]", "", key_raw)
            for k, v in FIELD_MAP.items():
                if k == key_clean or k in key_clean:  # Exact or very close match
                    db_key = v
                    break

            if db_key:
                # Extract value from html content
                match_obj = re.match(r"^([^\s：:]+[\s]*[：:])", para_html_content)
                if match_obj:
                    prefix = match_obj.group(1)
                    value = para_html_content[len(prefix) :].strip()
                else:
                    value = field_match.group(2).strip()

                current_record[db_key] = value
                current_field = db_key
            else:
                # Unknown key, treat as continuation
                if current_field:
                    if current_field == "name":
                        if current_record.get("transcript"):
                            current_record["transcript"] += "\n" + para_html_content
                        else:
                            current_record["transcript"] = para_html_content
                        current_field = "transcript"
                    else:
                        current_record[current_field] += "\n" + para_html_content
        else:
            # No key found, append to current field
            if current_field:
                if current_field == "name":
                    if current_record.get("transcript"):
                        current_record["transcript"] += "\n" + para_html_content
                    else:
                        current_record["transcript"] = para_html_content
                    current_field = "transcript"
                else:
                    current_record[current_field] += "\n" + para_html_content

    # Save last record
    finalize_record()

    return records


def process_import(file_path: str, db: Session):
    """
    Orchestrates the import process:
    1. Parse docx
    2. Check duplicates (by Name)
    3. Save new records
    4. Return report
    """
    try:
        if os.path.basename(file_path).startswith("~$"):
            return {
                "success": 0,
                "skipped": 0,
                "errors": [
                    f"{os.path.basename(file_path)} 看起来是 Word 临时锁文件（~$ 开头），请关闭 Word 后重试或直接删除该文件"
                ],
            }
        parsed_records = parse_docx(file_path)
    except Exception as e:
        import traceback

        traceback.print_exc()
        if isinstance(e, PackageNotFoundError):
            return {
                "success": 0,
                "skipped": 0,
                "errors": [
                    f"无法打开为有效的 .docx 包：{os.path.basename(file_path)}（常见原因：~$ 临时锁文件、文件未下载完整或文件损坏）"
                ],
            }
        return {"success": 0, "skipped": 0, "errors": [str(e)]}

    success_count = 0
    skipped_list = []
    processed_serials = set()

    for record in parsed_records:
        serial_num = record.get("serial_num")
        # 如果没有编号或没有名字，则跳过
        if not serial_num or not record.get("name"):
            continue

        # Check duplicate in current batch
        if serial_num in processed_serials:
            skipped_list.append(
                {
                    "serial_num": serial_num,
                    "name": record.get("name"),
                    "reason": "Duplicate Serial Number (in same document)",
                    "new_data": record,
                }
            )
            continue

        # Check duplicate in database
        exists = (
            db.query(Inscription).filter(Inscription.serial_num == serial_num).first()
        )
        if exists:
            skipped_list.append(
                {
                    "serial_num": serial_num,
                    "name": record.get("name"),
                    "reason": "Duplicate Serial Number (in DB)",
                    "existing_id": exists.id,
                    "new_data": record,  # Include full record data for potential overwrite
                }
            )
            continue

        # Save new record
        processed_serials.add(serial_num)
        db_obj = Inscription(**record)
        db.add(db_obj)
        success_count += 1

    db.commit()

    return {
        "success": success_count,
        "skipped": len(skipped_list),
        "skipped_items": skipped_list,
    }


def main():
    setup_database()
    db = SessionLocal()

    if not os.path.exists(RAW_DOCS_DIR):
        print(f"Directory {RAW_DOCS_DIR} not found.")
        return

    files = []
    for filename in os.listdir(RAW_DOCS_DIR):
        if filename.startswith("~$"):
            continue
        if not (filename.endswith(".docx") or filename.endswith(".doc")):
            continue

        path = os.path.join(RAW_DOCS_DIR, filename)
        if not os.path.isfile(path):
            continue

        files.append(filename)
    if not files:
        print(f"No Word files found in {RAW_DOCS_DIR}")

    for filename in files:
        path = os.path.join(RAW_DOCS_DIR, filename)
        print(f"Processing {filename}...")
        result = process_import(path, db)
        print(f"Result for {filename}: {result}")

    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
