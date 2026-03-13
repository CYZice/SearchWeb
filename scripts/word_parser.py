import os
import re
import json
import sys
from docx import Document
from sqlalchemy.orm import Session

# Add root to path
sys.path.append(os.getcwd())

from app.models import Base, Inscription
from app.database import engine, SessionLocal

# Constants
RAW_DOCS_DIR = "data/raw_word"
IMAGES_DIR = "app/static/images"
# Ensure we use the correct path separator for URLs (forward slash)
IMAGE_URL_PREFIX = "/static/images/"

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
    "释文": "transcript",
    "釋文": "transcript"
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
        'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    }
    
    if run.element is None:
        return images

    # Find drawing elements
    # Note: python-docx elements usually have nsmap
    drawings = run.element.findall('.//w:drawing', run.element.nsmap)
    
    for drawing in drawings:
        # Find blip
        blips = drawing.findall('.//a:blip', nsmap)
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
    clean_serial = re.sub(r'[^\w]', '', serial_num)
    if not clean_serial:
        clean_serial = "unknown"
        
    filename = f"{clean_serial}_{index}.{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)
    
    with open(filepath, "wb") as f:
        f.write(image_part.blob)
        
    return f"{IMAGE_URL_PREFIX}{filename}"

def parse_docx(file_path, db: Session):
    doc = Document(file_path)
    
    current_record = None
    current_field = None
    image_counter = 1
    
    # Regex for new record: 【017】 or [017]
    record_pattern = re.compile(r'^[【\[](\d+)[】\]]')
    
    # Regex for field: Key: Value
    # Handle Chinese colon and spaces
    field_pattern = re.compile(r'^([^\s：:]+)[\s]*[：:](.*)')

    def save_current_record():
        nonlocal current_record
        if current_record:
            # Convert image_list to JSON string
            if "image_list" in current_record:
                current_record["image_url"] = json.dumps(current_record["image_list"])
                del current_record["image_list"]
            
            # Create DB object
            db_obj = Inscription(**current_record)
            db.add(db_obj)
            print(f"Saved record: {current_record.get('serial_num')} - {current_record.get('name')}")
            current_record = None

    for para in doc.paragraphs:
        text = para.text.strip()
        
        # 1. Check for New Record Start
        match = record_pattern.match(text)
        if match:
            save_current_record()
            
            serial_num_str = match.group(0) # e.g., 【017】
            print(f"Found new record: {serial_num_str}")
            
            current_record = {
                "serial_num": serial_num_str,
                "image_list": []
            }
            image_counter = 1
            current_field = None
            continue
            
        # If we are not in a record yet, skip (or handle preamble)
        if current_record is None:
            continue
            
        # 2. Extract Images in this paragraph
        for run in para.runs:
            images = get_images_from_run(run, doc)
            for img_part in images:
                url = save_image(img_part, current_record['serial_num'], image_counter)
                current_record['image_list'].append(url)
                image_counter += 1
        
        # 3. Parse Text Fields
        if not text:
            continue
            
        field_match = field_pattern.match(text)
        if field_match:
            key_raw = field_match.group(1).strip()
            value = field_match.group(2).strip()
            
            # Find mapped key
            db_key = None
            for k, v in FIELD_MAP.items():
                if k in key_raw:
                    db_key = v
                    break
            
            if db_key:
                current_record[db_key] = value
                current_field = db_key
            else:
                # Unknown key, treat as continuation of previous field or ignore
                if current_field:
                    current_record[current_field] += "\n" + text
        else:
            # No key found, append to current field (e.g. multiline transcript)
            if current_field:
                current_record[current_field] += "\n" + text

    # Save last record
    save_current_record()
    db.commit()

def main():
    setup_database()
    db = SessionLocal()
    
    if not os.path.exists(RAW_DOCS_DIR):
        print(f"Directory {RAW_DOCS_DIR} not found.")
        return

    files = [f for f in os.listdir(RAW_DOCS_DIR) if f.endswith('.docx') or f.endswith('.doc')]
    if not files:
        print(f"No Word files found in {RAW_DOCS_DIR}")
    
    for filename in files:
        path = os.path.join(RAW_DOCS_DIR, filename)
        print(f"Processing {filename}...")
        try:
            parse_docx(path, db)
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            
    db.close()
    print("Done.")

if __name__ == "__main__":
    main()
