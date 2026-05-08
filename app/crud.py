from sqlalchemy.orm import Session
from sqlalchemy import or_, case
from . import models
import json
from typing import List
import zhconv


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


def get_timeline_data(db: Session, sample_size: int = 5):
    """Get inscriptions grouped by era for timeline view."""
    import re

    inscriptions = db.query(
        models.Inscription.era,
        models.Inscription.id,
        models.Inscription.name,
        models.Inscription.serial_num
    ).all()

    def extract_era_name(era_str):
        """从 era 字符串提取年号名称"""
        if not era_str:
            return None
        era_clean = re.sub(r'[（(][^）)]*[）)]', '', era_str)
        chinese_numerals = '一二三四五六七八九十百'

        # 特殊处理"期間"（不以年结尾）
        if era_clean.endswith('間') and not era_clean.endswith('月間'):
            return era_clean

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

    def extract_year_num(era_str):
        """从 era 字符串提取年份数字（如"三" -> 3）"""
        if not era_str:
            return 999
        chinese_to_arabic = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        era_clean = re.sub(r'[（(][^）)]*[）)]', '', era_str)
        # 找第一个中文字符数字
        for c in era_clean:
            if c in chinese_to_arabic:
                return chinese_to_arabic[c]
        return 999

    # 按提取的年号分组
    era_groups = {}
    for era, ins_id, name, serial_num in inscriptions:
        era_name = extract_era_name(era)
        if not era_name:
            continue
        if era_name not in era_groups:
            era_groups[era_name] = {"name": era_name, "count": 0, "samples": []}
        era_groups[era_name]["count"] += 1
        if len(era_groups[era_name]["samples"]) < sample_size:
            era_groups[era_name]["samples"].append({
                "id": ins_id,
                "name": name,
                "serial_num": serial_num,
                "_sort_key": extract_year_num(era)
            })

    # 对每个年号内的样本按年份排序
    for era_name in era_groups:
        era_groups[era_name]["samples"].sort(key=lambda x: x["_sort_key"])
        for item in era_groups[era_name]["samples"]:
            del item["_sort_key"]

    timeline_data = list(era_groups.values())

    # Historical era ordering
    ERA_ORDER = {
        "唐代": 0, "五代": 1, "五代十國": 1,
        "宋代": 10, "北宋": 11, "南宋": 12,
        "辽代": 20, "早期": 21,
        "天復": 30, "天赞": 31, "天顯": 32, "會同": 33, "天祿": 34,
        "景宗": 35, "乾亨": 36, "應曆": 37, "保寧": 38, "統和": 39,
        "開泰": 40, "太平": 41, "大康": 42, "大安": 43, "壽昌": 44,
        "乾統": 45, "天慶": 46, "天輔": 47,
        "金代": 50, "金": 51,
        "元代": 60, "元": 61,
        "明代": 70, "明": 71,
        "清代": 80, "清": 81,
    }

    def get_era_order(era_name):
        return ERA_ORDER.get(era_name, 100)

    return sorted(timeline_data, key=lambda x: get_era_order(x["name"]))


def get_all_eras(db: Session):
    """获取所有不重复的年号列表"""
    import re
    inscriptions = db.query(models.Inscription.era).all()
    eras = set()
    chinese_numerals = '一二三四五六七八九十百'

    for (era,) in inscriptions:
        if era:
            # 去掉括号内容（公元xxx年）
            era_clean = re.sub(r'[（(][^）)]*[）)]', '', era)

            # 特殊处理"月間"（时期）
            if era_clean.endswith('間') and not era_clean.endswith('月間'):
                # 如"保寧間" - "間"是时代名称的一部分
                eras.add(era_clean)
                continue

            # 找到年/月标记（不包含"年前"）
            last_marker_pos = -1
            for i in range(len(era_clean) - 1, -1, -1):
                c = era_clean[i]
                if c in ('年', '月') and not (i > 0 and era_clean[i-1] == '前'):
                    last_marker_pos = i
                    break

            if last_marker_pos == -1:
                if era_clean.strip():
                    eras.add(era_clean.strip())
                continue

            # 找到标记，往回找到数字部分开始的位置
            j = last_marker_pos - 1
            while j >= 0 and era_clean[j] in chinese_numerals:
                j -= 1
            # 跳过"元"（元年）
            if j >= 0 and era_clean[j] == '元':
                j -= 1

            era_name = era_clean[:j+1].strip()
            if era_name:
                eras.add(era_name)

    return sorted(list(eras))


def get_inscriptions_by_era(db: Session, era_name: str):
    """按年号名称筛选墓志"""
    # 使用模糊匹配，支持如"乾亨"、"乾統"等年号
    inscriptions = db.query(models.Inscription).filter(
        models.Inscription.era.like(f'%{era_name}%')
    ).all()
    return inscriptions
