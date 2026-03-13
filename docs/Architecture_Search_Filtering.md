# 架构设计文档: 碑文检索系统 - 字段级筛选功能

## 1. 影响范围分析 (Impact Analysis)

| 文件路径 | 修改类型 | 描述 |
| :--- | :--- | :--- |
| `app/crud.py` | **核心逻辑修改** | 重构 `search_inscriptions` 函数，使其支持动态字段列表构建 SQL 查询条件。 |
| `app/main.py` | **接口签名修改** | 更新 `/api/search` 路由处理函数，接收 `fields` 查询参数列表。 |
| `templates/index.html` | **UI/交互修改** | 新增复选框组组件；更新 `performSearch` 方法以组装新的 API 请求参数。 |

**上下文剪裁 (Context Pruning)**:
- **必须读取**: `app/crud.py`, `app/main.py`, `templates/index.html`
- **无需读取**: `app/models.py` (字段名已知), `app/database.py`, `scripts/*`

## 2. 接口定义 (Interface Definition)

### 后端层 (Backend)

**1. CRUD Layer (`app/crud.py`)**

```python
def search_inscriptions(
    db: Session, 
    query: str, 
    fields: List[str] = None,  # 新增参数
    skip: int = 0, 
    limit: int = 100
) -> List[models.Inscription]:
    """
    根据指定字段进行关键词检索。
    
    逻辑:
    1. 如果 fields 为空，使用默认集合 ['name', 'transcript', 'discovery']。
    2. 构建 OR 查询: WHERE field1 LIKE %q% OR field2 LIKE %q% ...
    3. 保持权重排序: 如果 'name' 在 fields 中，匹配 'name' 的结果排在前面。
    """
    pass
```

**2. API Layer (`app/main.py`)**

```python
from fastapi import Query

@app.get("/api/search")
def search(
    q: str, 
    fields: List[str] = Query(None), # 接收 ?fields=name&fields=era
    db: Session = Depends(get_db)
):
    # 调用 crud.search_inscriptions
    pass
```

### 前端层 (Frontend)

**API 请求格式**:
`GET /api/search?q=唐&fields=name&fields=era&fields=transcript`

**Vue State**:
```javascript
const selectedFields = ref(['name', 'transcript', 'discovery']) // 默认选中
```

## 3. 实施步骤 (Implementation Steps)

1.  **[Backend] 重构 CRUD 逻辑 (`app/crud.py`)**
    *   定义字段映射字典 `FIELD_MAP` (e.g., `{"name": models.Inscription.name}`).
    *   根据传入的 `fields` 列表动态生成 SQLAlchemy 的 `or_` 过滤条件。
    *   调整 `order_by` 逻辑，确保仅当 `name` 被选中时才应用名称优先排序。

2.  **[Backend] 更新 API 接口 (`app/main.py`)**
    *   引入 `Query` 类。
    *   修改 `search` 函数签名，添加 `fields` 参数。
    *   将 `fields` 传递给 CRUD 函数。

3.  **[Frontend] 实现 UI 组件 (`templates/index.html`)**
    *   在搜索框下方添加 8 个 Checkbox (器名, 时代, 别称, 释文, 出土, 现藏, 著录, 形制)。
    *   绑定 `v-model="selectedFields"`。

4.  **[Frontend] 更新调用逻辑 (`templates/index.html`)**
    *   修改 `performSearch` 方法。
    *   使用 `URLSearchParams` 构建带重复 key 的查询字符串 (fields)。

5.  **[Verification] 验证测试**
    *   测试默认搜索 (不勾选/默认勾选)。
    *   测试单字段搜索 (仅器名)。
    *   测试多字段搜索 (器名 + 时代)。