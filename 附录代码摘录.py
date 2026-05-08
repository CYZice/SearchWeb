# -*- coding: utf-8 -*-
"""
附录代码摘录 - 碑文金石资料检索系统

本文档包含论文附录所需的核心代码摘录，分为三个部分：
- 附录一：主要的数据库等后端代码
- 附录二：前端网页的主界面代码
- 附录三：网页后台管理界面代码
"""

# =============================================================================
# 附录一：主要的数据库等后端代码
# =============================================================================

# -------------------- 附录一.1 数据库配置 (app/database.py) --------------------
DATABASE_PY = '''
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database URL
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/inscriptions.db"

# Ensure the directory exists
os.makedirs("./data", exist_ok=True)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

# -------------------- 附录一.2 数据模型 (app/models.py) --------------------
MODELS_PY = '''
from sqlalchemy import Column, Integer, String, Text
from .database import Base


class Inscription(Base):
    __tablename__ = "inscriptions"

    id = Column(Integer, primary_key=True, index=True)
    serial_num = Column(String, index=True, unique=True)  # 文档编号
    name = Column(String, index=True)  # 器名 (核心检索字段)
    era = Column(String)  # 时代
    alias = Column(String)  # 别称
    discovery = Column(String)  # 出土/发现地
    collection = Column(String)  # 现藏地点
    publication = Column(String)  # 主要著录
    format = Column(String)  # 形制
    image = Column(Text)  # 图片出处/图版来源
    transcript = Column(Text)  # 释文
    image_url = Column(Text)  # 图片存储路径 (JSON list)
'''

# -------------------- 附录一.3 CRUD操作 (app/crud.py) --------------------
CRUD_PY = '''
from sqlalchemy.orm import Session
from sqlalchemy import or_, case
from . import models
import json
from typing import List
import zhconv


def search_inscriptions(
    db: Session, query: str, fields: List[str] = None, skip: int = 0, limit: int = 100
):
    """带权重搜索：Name匹配 > Transcript匹配 > Discovery匹配"""

    # 生成变体（原始、简体、繁体）
    variants = {query}
    try:
        variants.add(zhconv.convert(query, "zh-cn"))
        variants.add(zhconv.convert(query, "zh-tw"))
    except Exception:
        pass

    # 字段映射
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

    # 默认搜索字段
    if not fields:
        fields = ["name", "transcript", "discovery"]

    # 构建查询条件
    conditions = []
    for field in fields:
        if field in FIELD_MAP:
            field_matches = [FIELD_MAP[field].like(f"%{v}%") for v in variants]
            conditions.append(or_(*field_matches))

    # 优先级排序：Name匹配优先
    order_clauses = []
    if "name" in fields:
        name_matches = [models.Inscription.name.like(f"%{v}%") for v in variants]
        order_clauses.append((or_(*name_matches), 1))

    if order_clauses:
        ordering = case(*order_clauses, else_=2)
    else:
        ordering = None

    q = db.query(models.Inscription).filter(or_(*conditions))
    total_count = q.count()

    if ordering is not None:
        q = q.order_by(ordering, models.Inscription.serial_num)
    else:
        q = q.order_by(models.Inscription.serial_num)

    return q.offset(skip).limit(limit).all(), total_count


def create_inscription(db: Session, inscription_data: dict):
    """创建碑文记录"""
    if isinstance(inscription_data.get("image_url"), list):
        inscription_data["image_url"] = json.dumps(inscription_data["image_url"])

    db_item = models.Inscription(**inscription_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
'''

# -------------------- 附录一.4 词云服务 (app/services/wordcloud_service.py) --------------------
WORDCLOUD_SERVICE_PY = '''
from typing import Optional, List, Tuple
import io
import re
from collections import Counter

import jieba
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session
from wordcloud import WordCloud

STOPWORDS = {
    # 常见虚词和助词
    "的", "了", "是", "在", "有", "和", "与", "为", "于", "之",
    "而", "及", "或", "以", "等", "其", "所", "中", "上", "下",
    "不", "也", "这", "那", "被", "将", "从", "向", "对",
    "着", "过", "来", "去", "到", "会", "能", "可", "得", "如",
    # 时间表达式过滤
    "年", "月", "日", "时",
    # 碑文常用词过滤
    "碑", "文", "字", "石", "銘", "誌", "墓",
}

# 时间表达式正则
TIME_PATTERN = re.compile(r"^[\\\\d一二三四五六七八九十百千]+[年月日]$")


def get_all_transcripts(db: Session, era: Optional[str] = None) -> str:
    """获取所有碑文文本，可按时代筛选"""
    query = db.query(models.Inscription.transcript)
    if era:
        query = query.filter(models.Inscription.era == era)
    results = query.all()
    texts = [r[0] for r in results if r[0] and r[0].strip()]
    return " ".join(texts)


def tokenize_chinese(text: str) -> str:
    """使用jieba分词并过滤"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\\\\s+", " ", text)
    words = jieba.cut(text)
    filtered = [
        w for w in words
        if w not in STOPWORDS
        and len(w) > 1
        and not re.match(r"^[\\\\d\\\\s\\\\W]+$", w)
        and not TIME_PATTERN.match(w)
    ]
    return " ".join(filtered)


def generate_wordcloud_image(
    text: str,
    width: int = 1200,
    height: int = 800,
    background_color: str = "white",
    max_words: int = 200,
) -> bytes:
    """生成词云图片"""
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
'''

# -------------------- 附录一.5 FastAPI主入口 (app/main.py) --------------------
MAIN_PY = '''
from fastapi import FastAPI, Depends, HTTPException, Request, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import json
import os
import io

from . import models, crud, database
from .services import (
    get_all_transcripts,
    tokenize_chinese,
    generate_wordcloud_image,
    get_word_frequencies,
)

# Create tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Inscription Retrieval System")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/search")
def search(
    q: str,
    fields: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """碑文检索API"""
    skip = (page - 1) * size
    results, total_count = crud.search_inscriptions(
        db, q, fields=fields, skip=skip, limit=limit
    )
    for item in results:
        if item.image_url:
            try:
                item.image_url = json.loads(item.image_url)
            except:
                item.image_url = []
    return {"items": results, "total": total_count, "page": page, "size": size}


@app.get("/api/wordcloud")
def get_wordcloud(
    era: Optional[str] = Query(None),
    width: int = Query(1200),
    height: int = Query(800),
    max_words: int = Query(200),
    db: Session = Depends(get_db),
):
    """词云生成API"""
    transcripts = get_all_transcripts(db, era=era)
    if not transcripts or not transcripts.strip():
        from .services.wordcloud_service import _generate_empty_image
        img_bytes = _generate_empty_image(width, height)
    else:
        tokenized_text = tokenize_chinese(transcripts)
        img_bytes = generate_wordcloud_image(
            tokenized_text, width=width, height=height, max_words=max_words
        )
    return StreamingResponse(
        io.BytesIO(img_bytes),
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=wordcloud.png"},
    )


@app.get("/api/frequencies")
def get_word_frequencies_endpoint(
    era: Optional[str] = Query(None),
    top_n: int = Query(50),
    db: Session = Depends(get_db),
):
    """词频统计API"""
    transcripts = get_all_transcripts(db, era=era)
    frequencies = get_word_frequencies(transcripts, top_n=top_n)
    return {
        "frequencies": [{"word": word, "count": count} for word, count in frequencies]
    }


@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...), db: Session = Depends(get_db)
):
    """Word文档批量上传导入"""
    from scripts import word_parser
    total_success = 0
    total_skipped = 0
    errors = []

    for file in files:
        if not file.filename.endswith((".docx", ".doc")):
            errors.append(f"Skipped {file.filename}: Not a Word file")
            continue
        # ... 文件处理逻辑
    return {"success": total_success, "skipped": total_skipped, "errors": errors}
'''


# =============================================================================
# 附录二：前端网页的主界面代码
# =============================================================================

# -------------------- 附录二：前端主界面 (templates/index.html) --------------------
# 注意：由于HTML代码较长，此处摘录核心结构和JavaScript逻辑
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>辽代墓志检索数据库</title>
    <!-- Vue 3 -->
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <!-- ECharts -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>

    <style>
        :root {
            --paper-white: #F5F0E6;
            --paper-old: #E8DFD0;
            --vermilion: #C73E3A;
            --藏青: #1E3A5F;
        }
        /* 古籍古典风格样式... */
    </style>
</head>

<body>
    {% raw %}
    <div id="app">
        <!-- 搜索区域 -->
        <div class="mb-8">
            <input v-model="searchQuery" @keyup.enter="performSearch"
                   type="text" class="search-input" placeholder="输入检索关键词...">
            <button @click="performSearch" class="btn-search">检 索</button>
        </div>

        <!-- 字段选择 -->
        <div class="mt-4">
            <span v-for="field in fieldOptions" :key="field.value"
                  class="field-tag" :class="{ selected: selectedFields.includes(field.value) }"
                  @click="toggleField(field.value)">
                {{ field.label }}
            </span>
        </div>

        <!-- 统计面板（词云/词频） -->
        <div class="stats-panel" v-show="activeTab === 'wordcloud' || activeTab === 'frequencies'">
            <div v-if="activeTab === 'wordcloud'">
                <img :src="wordcloudUrl" alt="词云">
            </div>
            <div v-if="activeTab === 'frequencies'">
                <div id="frequencyChart" style="height: 400px;"></div>
            </div>
        </div>

        <!-- 搜索结果列表 -->
        <div v-for="item in results" :key="item.id" class="result-card" @click="openDetail(item)">
            <h2>{{ item.name }}</h2>
            <p>{{ item.era }} - {{ item.discovery }}</p>
        </div>
    </div>
    {% endraw %}

    <script>
    const { createApp, ref, nextTick, onMounted } = Vue

    createApp({
        setup() {
            const searchQuery = ref('')
            const results = ref([])
            const loading = ref(false)
            const selectedFields = ref(['name', 'transcript', 'discovery'])
            const activeTab = ref('search')
            let frequencyChart = null

            const fieldOptions = [
                { value: 'name', label: '器名' },
                { value: 'transcript', label: '誌文' },
                { value: 'discovery', label: '出土' },
                { value: 'era', label: '时代' },
                // ... 更多字段
            ]

            const toggleField = (field) => {
                const idx = selectedFields.value.indexOf(field)
                if (idx > -1) {
                    selectedFields.value.splice(idx, 1)
                } else {
                    selectedFields.value.push(field)
                }
            }

            const performSearch = async (page = 1) => {
                if (!searchQuery.value.trim()) return
                loading.value = true

                const params = new URLSearchParams()
                params.append('q', searchQuery.value)
                params.append('page', String(page))
                params.append('size', '15')
                selectedFields.value.forEach(field => {
                    params.append('fields', field)
                })

                const response = await fetch(`/api/search?${params.toString()}`)
                const data = await response.json()
                results.value = data.items || []
                totalResults.value = data.total || 0
                loading.value = false
            }

            const renderFrequencyChart = (frequencies, title = '词频统计 Top 15') => {
                // ECharts图表渲染
                frequencyChart = echarts.init(document.getElementById('frequencyChart'))
                frequencyChart.setOption({
                    title: { text: title, left: 'center' },
                    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
                    xAxis: { type: 'value', name: '出现次数' },
                    yAxis: { type: 'category', data: yData, name: '词语' },
                    series: [{
                        type: 'bar',
                        data: xData,
                        itemStyle: { color: new echarts.graphic.LinearGradient(...) }
                    }]
                })
            }

            return {
                searchQuery, results, loading, selectedFields, activeTab,
                toggleField, performSearch, renderFrequencyChart
            }
        }
    }).mount('#app')
    </script>
</body>
</html>
'''


# =============================================================================
# 附录三：网页后台管理界面代码
# =============================================================================

# -------------------- 附录三：后台管理界面 (templates/admin.html) --------------------
ADMIN_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>资料管理后台 - 碑文金石资料检索系统</title>
    <style>
        :root {
            --primary-color: #c0392b;
            --secondary-color: #2c3e50;
            --bg-color: #f9f9f9;
            --border-color: #ddd;
        }
        body { font-family: 'Segoe UI', sans-serif; background-color: var(--bg-color); }
        .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; }
        .tabs { display: flex; border-bottom: 1px solid var(--border-color); }
        .tab { padding: 10px 20px; cursor: pointer; border: 1px solid transparent; }
        .tab.active { background-color: white; border-color: var(--border-color); border-bottom-color: white; color: var(--primary-color); }
        .upload-area { border: 2px dashed var(--border-color); padding: 40px; text-align: center; border-radius: 8px; }
        .btn { background-color: var(--primary-color); color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .btn-danger { background-color: #e74c3c; }
        .data-table { width: 100%; border-collapse: collapse; }
        .data-table th, .data-table td { text-align: left; padding: 12px; border-bottom: 1px solid var(--border-color); }
        .loading-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.8); display: flex; justify-content: center; align-items: center; z-index: 1000; }
    </style>
</head>

<body>
    <div class="container">
        <header>
            <h1>资料管理后台</h1>
            <a href="/" class="nav-btn">← 返回检索首页</a>
        </header>

        <div class="tabs">
            <div class="tab active" onclick="switchTab('import')">资料导入</div>
            <div class="tab" onclick="switchTab('maintain')">数据维护</div>
        </div>

        <!-- 导入选项卡 -->
        <div id="import-section">
            <div class="upload-area" id="drop-zone">
                <h3>批量上传 Word 文档</h3>
                <p>支持 .docx 格式，可拖拽文件至此</p>
                <input type="file" id="file-input" multiple accept=".docx,.doc" style="display: none;">
                <button class="btn" onclick="document.getElementById('file-input').click()">选择文件</button>
            </div>
            <div id="upload-report" class="report-card">
                <h4>导入报告</h4>
                <div class="report-summary">
                    <span class="success-text">成功: <span id="success-count">0</span></span>
                    <span class="warning-text">跳过(重复): <span id="skipped-count">0</span></span>
                    <span class="error-text">错误: <span id="error-count">0</span></span>
                </div>
            </div>
        </div>

        <!-- 维护选项卡 -->
        <div id="maintain-section" style="display: none;">
            <div class="search-bar">
                <input type="text" id="maintain-search" placeholder="输入器名或编号搜索...">
                <button class="btn" onclick="searchData()">搜索</button>
            </div>
            <table class="data-table">
                <thead>
                    <tr><th>ID</th><th>器名</th><th>时代</th><th>操作</th></tr>
                </thead>
                <tbody id="data-list"></tbody>
            </table>
        </div>
    </div>

    <script>
        // 切换选项卡
        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelector(`.tab[onclick="switchTab(\\'' + tabName + '\\')"]`).classList.add('active');
            document.getElementById('import-section').style.display = tabName === 'import' ? 'block' : 'none';
            document.getElementById('maintain-section').style.display = tabName === 'maintain' ? 'block' : 'none';
            if (tabName === 'maintain') searchData();
        }

        // 文件上传处理
        const fileInput = document.getElementById('file-input');
        fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

        async function handleFiles(files) {
            if (files.length === 0) return;
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
            showLoading(true);
            try {
                const response = await fetch('/api/upload', { method: 'POST', body: formData });
                const result = await response.json();
                showReport(result);
            } catch (error) {
                alert('上传失败: ' + error.message);
            } finally {
                showLoading(false);
            }
        }

        function showReport(data) {
            document.getElementById('success-count').textContent = data.success;
            document.getElementById('skipped-count').textContent = data.skipped;
            document.getElementById('error-count').textContent = data.errors ? data.errors.length : 0;
        }

        // 数据搜索
        async function searchData() {
            const query = document.getElementById('maintain-search').value;
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const results = await response.json();
            const tbody = document.getElementById('data-list');
            tbody.innerHTML = '';
            results.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td>${item.id}</td><td>${item.name}</td><td>${item.era || '-'}</td>
                    <td><button class="btn btn-danger btn-small" onclick="deleteItem(${item.id})">删除</button></td>`;
                tbody.appendChild(tr);
            });
        }

        // 删除记录
        async function deleteItem(id) {
            if (!confirm(`确定要删除 ID:${id} 的记录吗？`)) return;
            await fetch(`/api/inscriptions/${id}`, { method: 'DELETE' });
            searchData();
        }

        function showLoading(show) {
            document.getElementById('loading').style.display = show ? 'flex' : 'none';
        }
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    print("附录代码摘录 - 碑文金石资料检索系统")
    print("=" * 60)
    print("附录一：主要的数据库等后端代码")
    print("  - app/database.py (数据库配置)")
    print("  - app/models.py (数据模型)")
    print("  - app/crud.py (CRUD操作)")
    print("  - app/services/wordcloud_service.py (词云服务)")
    print("  - app/main.py (FastAPI主入口)")
    print()
    print("附录二：前端网页的主界面代码")
    print("  - templates/index.html (Vue 3 + ECharts)")
    print()
    print("附录三：网页后台管理界面代码")
    print("  - templates/admin.html (资料导入/数据维护)")
    print()
    print("注意：本文件包含代码字符串定义，可直接导入使用或重新导出为独立文件")
