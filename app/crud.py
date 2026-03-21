from sqlalchemy.orm import Session
from sqlalchemy import or_, case
from . import models
import json
from typing import List
import zhconv


def get_inscriptions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Inscription).offset(skip).limit(limit).all()


def search_inscriptions(
    db: Session, query: str, fields: List[str] = None, skip: int = 0, limit: int = 100
):
    # Weighted search: Name match > Transcript match > Discovery match
    # Using case to assign weights for ordering

    # Generate variants (Original, Simplified, Traditional)
    variants = {query}
    try:
        variants.add(zhconv.convert(query, "zh-cn"))
        variants.add(zhconv.convert(query, "zh-tw"))
    except Exception:
        # Fallback if zhconv fails for any reason
        pass

    # Prepare patterns for LIKE query
    search_patterns = [f"%{v}%" for v in variants]

    # Define field mapping
    FIELD_MAP = {
        "name": models.Inscription.name,
        "era": models.Inscription.era,
        "alias": models.Inscription.alias,
        "transcript": models.Inscription.transcript,
        "discovery": models.Inscription.discovery,
        "collection": models.Inscription.collection,
        "publication": models.Inscription.publication,
        "format": models.Inscription.format,
        "image": models.Inscription.image,
    }

    # Default fields if none provided
    if not fields:
        fields = ["name", "transcript", "discovery"]

    # Build dynamic OR conditions
    # For each selected field, we check if it matches ANY of the variants
    conditions = []
    for field in fields:
        if field in FIELD_MAP:
            # Create OR condition for this field against all variants
            field_matches = [
                FIELD_MAP[field].like(pattern) for pattern in search_patterns
            ]
            conditions.append(or_(*field_matches))

    if not conditions:
        # Fallback if valid fields are empty after filtering
        # Default search across core fields with all variants
        core_fields = [
            models.Inscription.name,
            models.Inscription.transcript,
            models.Inscription.discovery,
        ]
        for f in core_fields:
            conditions.append(or_(*[f.like(p) for p in search_patterns]))

    # Priority logic in SQL
    # We want results where name matches ANY variant to appear first, ONLY if 'name' is in the selected fields
    order_clauses = []
    if "name" in fields:
        # Priority 1: Name matches exactly one of the variants
        name_matches = [models.Inscription.name.like(p) for p in search_patterns]
        order_clauses.append((or_(*name_matches), 1))

    # Add other cases if needed, or just default
    # For now, we stick to the requirement: "preserve 'name match priority' if name is selected"

    if order_clauses:
        ordering = case(*order_clauses, else_=2)
    else:
        ordering = (
            None  # No specific ordering based on match type if name is not selected
        )

    q = db.query(models.Inscription).filter(or_(*conditions))

    if ordering is not None:
        q = q.order_by(ordering)

    return q.offset(skip).limit(limit).all()


def get_inscription(db: Session, inscription_id: int):
    return (
        db.query(models.Inscription)
        .filter(models.Inscription.id == inscription_id)
        .first()
    )


def get_inscription_by_name(db: Session, name: str):
    return db.query(models.Inscription).filter(models.Inscription.name == name).first()


def create_inscription(db: Session, inscription_data: dict):
    # Ensure image_url is JSON string if it's a list
    if isinstance(inscription_data.get("image_url"), list):
        inscription_data["image_url"] = json.dumps(inscription_data["image_url"])

    db_item = models.Inscription(**inscription_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
