from sqlalchemy.orm import Session
from sqlalchemy import or_, case
from . import models
import json
import re
from typing import List
import zhconv


UNKNOWN_YEAR_SORT = 999999


ERA_ORDER = {
    "神册": 0,
    "神冊": 0,
    "天赞": 0,
    "天贊": 0,
    "天显": 1,
    "天顯": 1,
    "会同": 1,
    "會同": 1,
    "大同": 1,
    "天禄": 2,
    "天祿": 2,
    "应历": 3,
    "應曆": 3,
    "保宁": 4,
    "保寧": 4,
    "乾亨": 4,
    "统和": 5,
    "統和": 5,
    "统合": 5,
    "統合": 5,
    "开泰": 5,
    "開泰": 5,
    "太平": 5,
    "景福": 6,
    "重熙": 6,
    "清宁": 7,
    "清寧": 7,
    "咸雍": 7,
    "大康": 7,
    "大安": 7,
    "寿昌": 7,
    "壽昌": 7,
    "乾统": 8,
    "乾統": 8,
    "天庆": 8,
    "天慶": 8,
    "保大": 8,
    "未详": 9,
    "未詳": 9,
}


def get_inscriptions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Inscription).offset(skip).limit(limit).all()


def search_inscriptions(
    db: Session, query: str, fields: List[str] = None, skip: int = 0, limit: int = 100,
    sort_by: str = None, sort_order: str = "asc"
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
    total_count = q.count()

    # Apply sorting if specified
    SORTABLE_FIELDS = {
        "id": models.Inscription.id,
        "name": models.Inscription.name,
        "era": models.Inscription.era,
        "serial_num": models.Inscription.serial_num,
    }

    if sort_by and sort_by in SORTABLE_FIELDS:
        order_col = SORTABLE_FIELDS[sort_by]
        if sort_order == "desc":
            order_col = order_col.desc()
        q = q.order_by(order_col)
    elif ordering is not None:
        q = q.order_by(ordering, models.Inscription.serial_num)
    else:
        q = q.order_by(models.Inscription.serial_num)

    return q.offset(skip).limit(limit).all(), total_count


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


def update_inscription(db: Session, inscription_id: int, updates: dict):
    """部分更新单条记录"""
    db_obj = db.query(models.Inscription).filter(
        models.Inscription.id == inscription_id
    ).first()
    if not db_obj:
        return None
    for key, value in updates.items():
        if hasattr(db_obj, key) and key != 'id':
            setattr(db_obj, key, value)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def extract_era_name(era_str: str):
    """从 era 字符串提取年号名称"""
    if not era_str:
        return None
    era_clean = re.sub(r'[（(][^）)]*[）)]', '', era_str)
    chinese_numerals = '一二三四五六七八九十百'

    # 特殊处理"期間"（不以年结尾）
    if era_clean.endswith('間') and not era_clean.endswith('月間'):
        return era_clean[:-1].strip()

    # 找到最后一个"年"标记
    last_year_pos = -1
    for i in range(len(era_clean) - 1, -1, -1):
        if era_clean[i] == '年' and not (i > 0 and era_clean[i-1] == '前'):
            last_year_pos = i
            break

    if last_year_pos >= 0:
        j = last_year_pos - 1
        while j >= 0 and era_clean[j] in chinese_numerals:
            j -= 1
        if j >= 0 and era_clean[j] == '元':
            j -= 1
        return era_clean[:j+1].strip()
    return era_clean.strip()


def extract_year_num(era_str: str) -> int:
    """从 era 字符串提取最早公元年份（如"乾亨三年（公元981年）" -> 981）"""
    if not era_str:
        return UNKNOWN_YEAR_SORT

    match = re.search(r'(?:公元|西元)\s*(\d{3,4})\s*(?:年|[-－—至])', era_str)
    if match:
        return int(match.group(1))
    return UNKNOWN_YEAR_SORT


def get_era_order_index(era_name: str) -> int:
    """按辽代时期表返回年号组顺序，未知年号排在时期表之后。"""
    if not era_name:
        return UNKNOWN_YEAR_SORT
    return ERA_ORDER.get(era_name.strip(), UNKNOWN_YEAR_SORT)


def timeline_group_sort_key(era_group: dict):
    """时间轴年号组排序：最早年份优先，时期表顺序作为兜底。"""
    year_sort_key = era_group.get("_sort_key", UNKNOWN_YEAR_SORT)
    era_order_index = get_era_order_index(era_group["name"])
    if year_sort_key != UNKNOWN_YEAR_SORT:
        return (0, year_sort_key, era_order_index, era_group["name"])
    return (1, era_order_index, era_group["name"])




def get_timeline_data(db: Session, page: int = 1, page_size: int = 50, include_all: bool = False):
    """
    Get inscriptions grouped by era for timeline view.

    Args:
        db: Database session
        page: Page number (1-indexed)
        page_size: Number of eras per page
        include_all: If True, return all inscriptions for each era (not just samples)
    """
    inscriptions = db.query(
        models.Inscription.era,
        models.Inscription.id,
        models.Inscription.name,
        models.Inscription.serial_num
    ).all()

    # 按提取的年号分组
    era_groups = {}
    for era, ins_id, name, serial_num in inscriptions:
        era_name = extract_era_name(era)
        if not era_name:
            continue
        year_sort_key = extract_year_num(era)
        if era_name not in era_groups:
            era_groups[era_name] = {
                "name": era_name,
                "count": 0,
                "samples": [],
                "_sort_key": year_sort_key,
            }
        else:
            era_groups[era_name]["_sort_key"] = min(
                era_groups[era_name]["_sort_key"], year_sort_key
            )
        era_groups[era_name]["count"] += 1
        if include_all or len(era_groups[era_name]["samples"]) < 5:
            era_groups[era_name]["samples"].append({
                "id": ins_id,
                "name": name,
                "serial_num": serial_num,
                "_sort_key": year_sort_key
            })

    # 对每个年号内的样本按年份排序
    for era_name in era_groups:
        era_groups[era_name]["samples"].sort(
            key=lambda x: (x["_sort_key"], x["serial_num"] or "")
        )
        for item in era_groups[era_name]["samples"]:
            del item["_sort_key"]

    timeline_data = sorted(list(era_groups.values()), key=timeline_group_sort_key)
    for era in timeline_data:
        del era["_sort_key"]

    # 计算总墓志数
    total_inscriptions = sum(era["count"] for era in timeline_data)

    # 分页
    total_eras = len(timeline_data)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_eras = timeline_data[start_idx:end_idx]

    return {
        "eras": paginated_eras,
        "total_eras": total_eras,
        "total_inscriptions": total_inscriptions,
        "page": page,
        "page_size": page_size,
        "has_more": end_idx < total_eras
    }



def get_inscriptions_by_era(db: Session, era_name: str):
    """按年号名称筛选墓志"""
    # 使用模糊匹配，支持如"乾亨"、"乾統"等年号
    inscriptions = db.query(models.Inscription).filter(
        models.Inscription.era.like(f'%{era_name}%')
    ).all()
    return inscriptions
