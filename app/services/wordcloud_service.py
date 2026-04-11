from typing import Optional, List, Tuple
import io
import re
from collections import Counter

import jieba
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session
from wordcloud import WordCloud

from .. import models

import os

CHINESE_FONT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "static", "fonts", "NotoSansCJK-Thin.ttc"
)

STOPWORDS = {
    # Common Chinese particles and function words
    "的", "了", "是", "在", "有", "和", "与", "为", "于", "之",
    "而", "及", "或", "以", "等", "其", "所", "中", "上", "下",
    "不", "也", "这", "那", "被", "将", "从", "向", "对",
    "着", "过", "来", "去", "到", "会", "能", "可", "得", "如",
    "但", "却", "又", "就", "都", "还", "已", "曾",
    # Numbers (single digit)
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    # Time-related words
    "年", "月", "日", "时", "时间", "五年", "四月",
    # Common inscription-specific words to filter
    "碑", "文", "字", "石", "銘", "誌", "墓",
    # Punctuation and symbols
    "、", "。", "，", "；", "：", "！", "？", "「", "」", "『", "』",
    "（", "）", "（", "）", "《", "》", "〈", "〉",
    "——", "……", "——", "～", "□", "■", "□",
    # Whitespace
    "\n", "\r", "\t", " ",
}

# Regex to match time expressions like 二年、三年、五年、四月、二日
TIME_PATTERN = re.compile(r"^[\d一二三四五六七八九十百千]+[年月日]$")


def get_all_transcripts(db: Session, era: Optional[str] = None) -> str:
    """Fetch all transcript text from inscriptions, optionally filtered by era."""
    query = db.query(models.Inscription.transcript)
    if era:
        query = query.filter(models.Inscription.era == era)
    results = query.all()
    texts = [r[0] for r in results if r[0] and r[0].strip()]
    return " ".join(texts)


def clean_text(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    # Remove HTML tags (img tags, etc.)
    text = re.sub(r"<[^>]+>", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize_chinese(text: str) -> str:
    """Use jieba to tokenize Chinese text into words."""
    # Clean HTML tags first
    text = clean_text(text)
    words = jieba.cut(text)
    # Filter: not in stopwords, length > 1, not purely punctuation/digits, not time expressions
    filtered = [
        w
        for w in words
        if w not in STOPWORDS
        and len(w) > 1
        and not re.match(r"^[\d\s\W]+$", w)
        and not TIME_PATTERN.match(w)
    ]
    return " ".join(filtered)


def get_word_frequencies(text: str, top_n: int = 50) -> List[Tuple[str, int]]:
    """Get word frequencies from text. Returns list of (word, count) tuples."""
    text = clean_text(text)
    words = jieba.cut(text)
    filtered = [
        w
        for w in words
        if w not in STOPWORDS
        and len(w) > 1
        and not re.match(r"^[\d\s\W]+$", w)
        and not TIME_PATTERN.match(w)
    ]
    return Counter(filtered).most_common(top_n)


def generate_wordcloud_image(
    text: str,
    width: int = 1200,
    height: int = 800,
    background_color: str = "white",
    max_words: int = 200,
) -> bytes:
    """Generate a word cloud image from Chinese text. Returns PNG bytes."""
    if not text or not text.strip():
        return _generate_empty_image(width, height)

    wordcloud = WordCloud(
        width=width,
        height=height,
        background_color=background_color,
        font_path=CHINESE_FONT_PATH,
        max_words=max_words,
        prefer_horizontal=0.7,
        min_font_size=10,
    )

    wordcloud.generate(text)

    img_buffer = io.BytesIO()
    wordcloud.to_image().save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return img_buffer.getvalue()


def _generate_empty_image(width: int, height: int) -> bytes:
    """Generate placeholder image when no text is available."""
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(CHINESE_FONT_PATH, 40)
    except Exception:
        font = ImageFont.load_default()

    message = "No Data / 暂无数据"
    bbox = draw.textbbox((0, 0), message, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    position = ((width - text_width) // 2, (height - text_height) // 2)
    draw.text(position, message, fill="gray", font=font)

    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return img_buffer.getvalue()


def get_official_titles_text() -> str:
    """读取官称文档内容"""
    official_titles_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "官称.md"
    )
    try:
        with open(official_titles_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def get_official_titles_set() -> set:
    """读取官称文档，返回词语集合"""
    text = get_official_titles_text()
    words = text.split()
    return set(w.strip() for w in words if w.strip())
