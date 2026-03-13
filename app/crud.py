from sqlalchemy.orm import Session
from sqlalchemy import or_, case
from . import models
import json
from typing import List

def get_inscriptions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Inscription).offset(skip).limit(limit).all()

def search_inscriptions(db: Session, query: str, fields: List[str] = None, skip: int = 0, limit: int = 100):
    # Weighted search: Name match > Transcript match > Discovery match
    # Using case to assign weights for ordering
    search_pattern = f"%{query}%"
    
    # Define field mapping
    FIELD_MAP = {
        "name": models.Inscription.name,
        "era": models.Inscription.era,
        "alias": models.Inscription.alias,
        "transcript": models.Inscription.transcript,
        "discovery": models.Inscription.discovery,
        "collection": models.Inscription.collection,
        "publication": models.Inscription.publication,
        "format": models.Inscription.format
    }

    # Default fields if none provided
    if not fields:
        fields = ["name", "transcript", "discovery"]
    
    # Build dynamic OR conditions
    conditions = []
    for field in fields:
        if field in FIELD_MAP:
            conditions.append(FIELD_MAP[field].like(search_pattern))
            
    if not conditions:
        # Fallback if valid fields are empty after filtering
        conditions = [
            models.Inscription.name.like(search_pattern),
            models.Inscription.transcript.like(search_pattern),
            models.Inscription.discovery.like(search_pattern)
        ]

    # Priority logic in SQL
    # We want results where name matches to appear first, ONLY if 'name' is in the selected fields
    order_clauses = []
    if "name" in fields:
        order_clauses.append((models.Inscription.name.like(search_pattern), 1))
    
    # Add other cases if needed, or just default
    # For now, we stick to the requirement: "preserve 'name match priority' if name is selected"
    
    if order_clauses:
        ordering = case(*order_clauses, else_=2)
    else:
        ordering = None # No specific ordering based on match type if name is not selected

    q = db.query(models.Inscription).filter(or_(*conditions))
    
    if ordering is not None:
        q = q.order_by(ordering)
        
    return q.offset(skip).limit(limit).all()

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
