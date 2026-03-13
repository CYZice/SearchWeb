# 碑文金石资料检索系统 (Inscription Retrieval System)

## 项目简介
本项目旨在为约 300 篇金石碑文资料建立一个结构化的数字化检索平台。

## 技术栈
- **后端**: FastAPI + SQLite
- **前端**: HTML + Jinja2 Templates (Vue.js optional via CDN)
- **部署**: Docker

## 目录结构
- `app/`: 核心代码
- `data/`: 数据文件 (Word 原稿, SQLite DB)
- `scripts/`: 工具脚本 (Word 解析器)
- `docker/`: Docker 配置

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 初始化数据
将 Word 文档放入 `data/raw_word/` 目录，然后运行：
```bash
python scripts/word_parser.py
```

### 3. 启动服务
```bash
uvicorn app.main:app --reload
```
访问 http://127.0.0.1:8000 查看首页。

### 4. Docker 部署
```bash
docker-compose up --build
```
