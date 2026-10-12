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
from pydantic import BaseModel, Field

app = FastAPI(
    title="StockSignal FastAPI Slice",
    version="0.2.0",
    description="T-267/268：ASGI 增量切片（health + 只读数据 + 星辰 AI 服务层：知识库/意图/对话）",
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


# ══════════════ T-268 星辰 AI 服务层（知识库 / 意图 / 对话） ══════════════
# AI 能力服务化：知识库检索与意图路由是无状态纯函数（零网络），FastAPI 进程内
# 直调；完整对话（ai_answer，含实时行情抓取）经 asyncio.to_thread 走 full 模式。

from modules import knowledge_base as kb  # noqa: E402
from mcp_server.gateway import detect_intent  # noqa: E402


class ChatIn(BaseModel):
    """对话请求体（Pydantic 校验示范：长度/模式约束声明式）。"""
    question: str = Field(min_length=1, max_length=2000, description="用户问题")
    mode: str = Field("fast", pattern=r"^(fast|full)$",
                      description="fast=知识库+意图路由（秒回）；full=完整 ai_answer（含实时取数，较慢）")


@app.post("/api/ai/chat", tags=["ai"])
async def ai_chat(body: ChatIn) -> dict:
    """星辰 AI 对话端点。

    - fast（默认）：知识库检索 → 未命中走意图路由提示，纯本地零网络，毫秒级；
    - full：完整 ai_answer 链路（股票解析/实时行情/LLM/规则引擎），耗时可达数十秒。
    诚实语义：取不到数据如实返回 unavailable，绝不编造。
    """
    q = body.question.strip()
    if body.mode == "fast":
        kb_ans = kb.answer(q)
        if kb_ans:
            return {"status": "ok", "source": "knowledge_base", "answer": kb_ans}
        intent = detect_intent(q)
        if intent.get("tool") and intent.get("confidence", 0) >= 0.85:
            return {"status": "ok", "source": "intent",
                    "answer": f"检测到「{intent['tool']}」意图（置信度 {intent['confidence']:.2f}）。"
                              f"该意图需要实时数据链路，请用 mode=full 或在星辰 AI 页面提问。",
                    "intent": intent}
        return {"status": "ok", "source": "fallback",
                "answer": "未命中知识库与工具意图。请在星辰 AI 页面用完整模式提问，"
                          "或换一种问法（例：「什么是市盈率」「仓位怎么定」「49.1% 是什么口径」）。"}
    import asyncio
    from modules.ai_engine import ai_answer
    result = await asyncio.wait_for(
        asyncio.to_thread(ai_answer, q, None), timeout=90.0)
    return {"status": "ok", "source": "ai_engine",
            "answer": result.get("answer", ""),
            "independent": result.get("independent", True)}


@app.get("/api/ai/knowledge/search", tags=["ai"])
def knowledge_search(
    q: str = Query(min_length=1, max_length=200, description="检索问题"),
) -> dict:
    """金融知识库检索（含项目专属数据口径条目）。"""
    hit = kb.search(q)
    if not hit:
        return {"status": "ok", "found": False, "stats": kb.stats()}
    e = hit["entry"]
    return {"status": "ok", "found": True, "score": hit["score"],
            "data": {"id": e["id"], "category": e["cat"], "title": e["title"],
                     "content": e["content"]}}


@app.get("/api/ai/knowledge/stats", tags=["ai"])
def knowledge_stats() -> dict:
    """知识库自省：条目数与分类分布。"""
    return {"status": "ok", "data": kb.stats()}


@app.get("/api/ai/intents", tags=["ai"])
def ai_intents() -> dict:
    """意图路由规则自省（mcp_server.gateway 的工具触发词清单）。"""
    from mcp_server.gateway import _INTENT_RULES
    rules = [{"tool": t, "keywords": r["keywords"], "needs_code": r.get("needs_code", False)}
             for t, r in _INTENT_RULES.items()]
    return {"status": "ok", "data": rules, "count": len(rules)}
