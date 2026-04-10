# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 碑文金石资料检索系统 (Inscription Retrieval System)

## 项目概述

碑文金石资料检索系统 - 一个用于金石碑文资料的数字化检索与管理平台，支持 Word 文档批量导入、字段级筛选搜索、词云统计和词频分析。

## 常用命令

### 安装与启动
```bash
pip install -r requirements.txt          # 安装依赖
uvicorn app.main:app --reload            # 本地开发服务器 (http://127.0.0.1:8000)
docker-compose up --build                # Docker 部署
```

### 数据导入
```bash
python scripts/word_parser.py            # 解析 data/raw_word/ 目录下的 Word 文档并导入数据库
```

### API 端点
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/` | 首页 |
| GET | `/admin` | 后台管理页面 |
| GET | `/api/search?q=关键词&fields=name&fields=era` | 搜索（fields 参数可选） |
| GET | `/api/inscriptions/{id}` | 获取单条记录 |
| GET | `/api/wordcloud?era=唐代&width=1200&height=800` | 生成词云图片 |
| GET | `/api/frequencies?era=唐代&top_n=50` | 获取词频统计 |
| POST | `/api/upload` | 上传 Word 文件批量导入 |
| POST | `/api/inscriptions/overwrite` | 覆盖更新已有记录 |
| DELETE | `/api/inscriptions/{id}` | 删除记录 |

## 架构设计

### 分层架构
```
Client (Browser) → API Layer (FastAPI) → Business Logic (CRUD/Services) → Data Access (SQLAlchemy) → SQLite
```

### 核心模块
- **`app/main.py`** - FastAPI 应用入口，路由定义
- **`app/crud.py`** - 数据库 CRUD 操作，包含带权重搜索（name > transcript > discovery）
- **`app/models.py`** - SQLAlchemy 模型定义（Inscription 表）
- **`app/database.py`** - 数据库连接配置
- **`app/services/`** - 业务服务层（词云生成、词频统计）
- **`app/services/wordcloud_service.py`** - 词云和词频分析实现（使用 jieba 分词）
- **`scripts/word_parser.py`** - Word 文档解析器，支持图片提取和繁简转换
- **`templates/index.html`** - 搜索前端（Vue.js 3 + ECharts + Tailwind CDN）
- **`templates/admin.html`** - 后台管理页面

### 数据模型
`inscriptions` 表核心字段：
- `id` (PK), `serial_num` (编号), `name` (器名，检索权重最高)
- `era` (时代), `alias` (别称), `discovery` (出土), `collection` (现藏)
- `publication` (著录), `format` (形制), `image` (图片来源), `transcript` (释文)
- `image_url` (图片路径，JSON 列表格式存储)

### 搜索特性
- **权重排序**：name 匹配 > transcript 匹配 > discovery 匹配
- **繁简转换**：自动支持简体中文、繁体中文变体搜索
- **字段筛选**：可指定搜索字段组合（name, era, alias, transcript, discovery, collection, publication, format, image）

### 词云与词频
- `/api/wordcloud` 返回 PNG 图片，支持按时代（era）筛选
- `/api/frequencies` 返回 JSON 格式的词频统计数据
- 使用 jieba 分词，包含中文停用词过滤（的、了、是、在、和、碑、文、字、石等）

### Word 导入流程
`word_parser.py` 的 `process_import()` 函数：
1. 解析 Word 文档（提取文本和图片）
2. 以 `serial_num`（编号）查重
3. 新记录写入数据库，冲突记录跳过并报告
4. 小于 50KB 的图片作为行内字符处理

## 技术栈
- **后端**：FastAPI 0.109.0, SQLAlchemy 2.0.25, uvicorn 0.27.0
- **数据库**：SQLite（`data/inscriptions.db`）
- **文档解析**：python-docx 1.1.0
- **中文处理**：zhconv 1.4.3（繁简转换），jieba 0.42.1（分词）
- **可视化**：WordCloud 1.9.3, ECharts 5.4.3, Tailwind CSS
- **前端**：Jinja2 模板 + Vue.js 3 (CDN)
