from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import json

from . import models, crud, database

# Create tables
models.Base.metadata.create_all(bind=database.engine)

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
def search(q: str, fields: Optional[List[str]] = Query(None), db: Session = Depends(get_db)):
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
