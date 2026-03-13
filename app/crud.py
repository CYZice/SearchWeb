from sqlalchemy.orm import Session
from sqlalchemy import or_, case
from . import models
import json

def get_inscriptions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Inscription).offset(skip).limit(limit).all()

def search_inscriptions(db: Session, query: str, skip: int = 0, limit: int = 100):
    # Weighted search: Name match > Transcript match > Discovery match
    # Using case to assign weights for ordering
    search_pattern = f"%{query}%"
    
    # Priority logic in SQL
    # We want results where name matches to appear first
    
    stmt = db.query(models.Inscription).filter(
        or_(
            models.Inscription.name.like(search_pattern),
            models.Inscription.transcript.like(search_pattern),
            models.Inscription.discovery.like(search_pattern)
        )
    ).order_by(
        case(
            (models.Inscription.name.like(search_pattern), 1),
            (models.Inscription.transcript.like(search_pattern), 2),
            else_=3
        )
    ).offset(skip).limit(limit)
    
    return stmt.all()

def get_inscription(db: Session, inscription_id: int):
    return db.query(models.Inscription).filter(models.Inscription.id == inscription_id).first()

def create_inscription(db: Session, inscription_data: dict):
    # Ensure image_url is JSON string if it's a list
    if isinstance(inscription_data.get("image_url"), list):
        inscription_data["image_url"] = json.dumps(inscription_data["image_url"])
        
    db_item = models.Inscription(**inscription_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
