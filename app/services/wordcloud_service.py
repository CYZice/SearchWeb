from typing import Optional, List, Tuple
import io
import re
import time
import hashlib
from collections import Counter
from functools import lru_cache
from threading import Lock

import jieba
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session
from wordcloud import WordCloud

from .. import models

import os

CHINESE_FONT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "static", "fonts", "NotoSansCJK-Thin.ttc"
)

# ========== TTL Cache Implementation ==========

class TTLCache:
    """Simple thread-safe TTL cache."""

    def __init__(self, ttl_seconds: int = 300):  # 默认 5 分钟缓存
        self._cache: dict = {}
        self._timestamps: dict = {}
        self._ttl = ttl_seconds
        self._lock = Lock()

    def _make_key(self, **kwargs) -> str:
        """生成缓存 key"""
        # 按字典序排序确保一致性
        items = sorted(kwargs.items())
        key_str = str(items)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, **kwargs) -> Optional[any]:
        """获取缓存，不存在或过期返回 None"""
        key = self._make_key(**kwargs)
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps[key] < self._ttl:
                    return self._cache[key]
                # 已过期，删除
                del self._cache[key]
                del self._timestamps[key]
        return None

    def set(self, value: any, **kwargs):
        """设置缓存"""
        key = self._make_key(**kwargs)
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def invalidate(self, **kwargs):
        """手动失效某个缓存"""
        key = self._make_key(**kwargs)
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()


# 全局缓存实例
_wordcloud_cache = TTLCache(ttl_seconds=300)  # 词云缓存 5 分钟
_frequencies_cache = TTLCache(ttl_seconds=300)  # 词频缓存 5 分钟
_data_cache = TTLCache(ttl_seconds=60)  # 原始数据缓存 1 分钟（防频繁查询数据库）

STOPWORDS = {
    # Common Chinese particles and function words
    "的", "了", "是", "在", "有", "和", "与", "为", "于", "之",
    "而", "及", "或", "以", "等", "其", "所", "中", "上", "下",
    "不", "也", "这", "那", "被", "将", "从", "向", "对",
    "着", "过", "来", "去", "到", "会", "能", "可", "得", "如",
    "但", "却", "又", "就", "都", "还", "已", "曾",
    # Numbers (single digit)
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    # Common inscription-specific words to filter
    "碑", "文", "字", "石", "銘", "誌", "墓",
    # Punctuation and symbols
    "、", "。", "，", "；", "：", "！", "？", "「", "」", "『", "』",
    "（", "）", "（", "）", "《", "》", "〈", "〉",
    "——", "……", "——", "～", "□", "■", "□",
    # Whitespace
    "\n", "\r", "\t", " ",
}


def get_all_transcripts(db: Session, era: Optional[str] = None) -> str:
    """Fetch all transcript text from inscriptions, optionally filtered by era."""
    # 尝试从缓存获取
    cached = _data_cache.get(era=era or "")
    if cached is not None:
        return cached

    query = db.query(models.Inscription.transcript)
    if era:
        query = query.filter(models.Inscription.era == era)
    results = query.all()
    texts = [r[0] for r in results if r[0] and r[0].strip()]
    result = " ".join(texts)

    # 存入缓存
    _data_cache.set(result, era=era or "")
    return result


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
    # Filter: not in stopwords, length > 1, not purely punctuation/digits
    filtered = [
        w
        for w in words
        if w not in STOPWORDS
        and len(w) > 1
        and not re.match(r"^[\d\s\W]+$", w)
    ]
    return " ".join(filtered)


def get_word_frequencies(text: str, top_n: int = 50) -> List[Tuple[str, int]]:
    """Get word frequencies from text. Returns list of (word, count) tuples."""
    # 尝试从缓存获取
    cache_key_data = {"text_len": len(text), "top_n": top_n}
    cached = _frequencies_cache.get(**cache_key_data)
    if cached is not None:
        return cached

    text = clean_text(text)
    words = jieba.cut(text)
    filtered = [
        w
        for w in words
        if w not in STOPWORDS
        and len(w) > 1
        and not re.match(r"^[\d\s\W]+$", w)
    ]
    result = Counter(filtered).most_common(top_n)

    # 存入缓存
    _frequencies_cache.set(result, **cache_key_data)
    return result


def generate_wordcloud_image(
    text: str,
    width: int = 1200,
    height: int = 800,
    background_color: str = "white",
    max_words: int = 200,
) -> bytes:
    """Generate a word cloud image from Chinese text. Returns PNG bytes."""
    # 尝试从缓存获取（基于文本长度+尺寸生成 key 的前 32 位作为简化 key）
    cache_key_data = {
        "text_len": len(text),
        "width": width,
        "height": height,
        "max_words": max_words,
    }
    cached = _wordcloud_cache.get(**cache_key_data)
    if cached is not None:
        return cached

    if not text or not text.strip():
        result = _generate_empty_image(width, height)
        _wordcloud_cache.set(result, **cache_key_data)
        return result

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
    result = img_buffer.getvalue()

    # 存入缓存
    _wordcloud_cache.set(result, **cache_key_data)
    return result


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


def invalidate_cache():
    """清除所有词云和词频缓存（在数据更新时调用）"""
    _wordcloud_cache.clear()
    _frequencies_cache.clear()
    _data_cache.clear()
