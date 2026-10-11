"""backend_fastapi —— T-267 FastAPI 试点切片（增量路线示范）。

定位与边界（诚实红线）
----------------------
* 存量 Flask 后端（backend/app.py，~80 路由，JWT/CORS/限流/审计齐全）**不是垃圾**，
  全量重写成本 >> 收益，维持生产。本包是「**新端点用 FastAPI 增量**」的示范切片：
  ASGI/异步、Pydantic 类型校验（替代 Flask 手写 isinstance 分支）、自动 OpenAPI
  文档（替代手写 openapi.py 契约表）。
* 与 Flask 共用同一个 SQLite 库（STOCKSIGNAL_API_DB 只读连接），零业务逻辑重复，
  所有查询 SELECT-only，试点不写任何表。
* 端口 5052（与 Flask 5050 / Streamlit 8501 错开），dev 启动：
  ``uv run uvicorn backend_fastapi.main:app --port 5052``
* 文档：/docs（Swagger UI，自动生成）——Flask 侧 openapi.py 需手工维护契约表，
  此处由类型注解自动产出，代码即文档。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

app = FastAPI(
    title="StockSignal FastAPI Slice",
    version="0.1.0",
    description="T-267 试点：ASGI 增量切片（health + 只读数据端点，Pydantic 校验 + 自动 OpenAPI）",
)


def _db_path() -> Path:
    """与 backend/config.py 同源的数据库路径（可被 STOCKSIGNAL_API_DB 覆盖）。"""
    env = os.environ.get("STOCKSIGNAL_API_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "backend" / "data" / "app.db"


def _readonly_query(sql: str, params: tuple = ()) -> list[dict]:
    """SELECT-only 只读查询（试点安全边界：绝不写库）。"""
    p = _db_path()
    if not p.exists():
        raise HTTPException(status_code=503, detail=f"database not found: {p.name}")
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


@app.get("/api/health", tags=["ops"])
def health() -> dict:
    """健康检查（与 Flask /api/health 同语义，供对比基准）。"""
    return {
        "status": "ok",
        "service": "fastapi-slice",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/fastapi/stock/{code}", tags=["demo"])
def stock_lookup(code: str) -> dict:
    """个股信息只读查询——Pydantic/FastAPI 路径校验示范。

    Flask 侧同语义端点需要手写：if not re.fullmatch(r"\\d{6}", code): return fail(...)；
    此处由路径约束声明式完成，非法输入自动 422 + 结构化错误体 + 自动进 OpenAPI 文档。
    """
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=422, detail="code must be 6 digits")
    rows = _readonly_query(
        "SELECT symbol, name FROM stocks WHERE symbol LIKE ? LIMIT 1",
        (f"%{code}",),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="stock not found")
    return {"status": "ok", "data": rows[0]}


@app.get("/api/fastapi/orders", tags=["demo"])
def list_orders(
    limit: int = Query(20, ge=1, le=200, description="每页条数（1-200）"),
    offset: int = Query(0, ge=0, description="偏移量"),
    status: str | None = Query(None, pattern=r"^(filled|rejected|pending)$",
                               description="订单状态过滤"),
) -> dict:
    """订单流水只读分页——Query 参数校验示范（ge/le/pattern 全部声明式）。"""
    where, params = "1=1", [limit, offset]
    if status:
        where, params = "status = ?", [status, limit, offset]
    try:
        rows = _readonly_query(
            f"SELECT * FROM real_orders WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            tuple(params),
        )
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=503, detail=f"table unavailable: {e}") from e
    return {"status": "ok", "data": rows, "count": len(rows)}
