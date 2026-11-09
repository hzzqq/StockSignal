# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/api/read_routes.py — W1 只读数据端点（前端 v2 替代 12 个绕过 API 的 Streamlit 页）

背景：legacy Streamlit 前端有 12 个页面直接读本地磁盘文件（data/ 等），新 React
前端（frontend-v2）要替换它们，需要把这些本地数据源用统一信封包成只读 REST 端点，
置于 JWT 鉴权之后。本蓝图**只读取、绝不写/改**任何数据文件。

安全约束（防穿越）：
  - 固定白名单端点：路径在代码里写死为绝对允许路径，用户无法注入路径段；
  - 参数化端点（按 date / user 拼路径）：用正则管形状 + 拼接后解析路径必须落在
    允许根目录（data/）内，越界一律 400 validation_error，绝不 open 任意路径。

覆盖映射（12 页 -> 本地数据源）：
  - 54 今日决策面板、90 登录、98 仓位落地 -> daily_snapshot.json
  - 54 今日决策面板、51 每日晨报   -> p1_signals/ (signal_*.json)
  - 97 决策回放                  -> snapshots/<date>.json (+ 日期清单)
  - 36 每日荐股                  -> daily_recommendation.json (+ reports/virtual_users_sim.json)
  - 42 模拟交易                  -> paper_<user>.json
  - 51 每日晨报                  -> review_notes_<date>.md
  - 73 自定义看板                -> user_dashboard.json
  - 74 告警引擎                  -> alert_rules.json / alerts.log
  - 86 网页作品集                -> webapps/*/meta.json（扩展允许根为 webapps/）

未能映射的页（数据源非本地 JSON 文件，已向 lead 说明）：
  - 47 价格预警：数据来自后端 API/SQLite（自选股、预警记录），非本地文件；
  - 93 系统配置：数据来自后端 admin/config API 与 cache.db/news.db，非本地 JSON。
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import fail, ok
from modules.site_config import CALL_TIMEOUT_CAP

# T-245：六维排雷「高危」等级字面量（与 modules.stock_risk.RISK_HIGH 对齐）
_RISK_HIGH = "high"

bp = Blueprint("read", __name__, url_prefix="/api/v2/read")

# 项目根 = backend/api/read_routes.py 的 parents[2]
_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = (_ROOT / "data").resolve()
_REPORTS_DIR = (_ROOT / "reports").resolve()
_WEBAPPS_DIR = (_ROOT / "webapps").resolve()

# 固定白名单：端点 key -> 绝对允许路径（仅本地只读，绝不写出）
_FILE_WHITELIST = {
    "daily_snapshot": _DATA_DIR / "daily_snapshot.json",
    "daily_recommendation": _DATA_DIR / "daily_recommendation.json",
    "user_dashboard": _DATA_DIR / "user_dashboard.json",
    "alert_rules": _DATA_DIR / "alert_rules.json",
    "alert_log": _DATA_DIR / "alerts.log",
    "virtual_users_sim": _REPORTS_DIR / "virtual_users_sim.json",
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_USER_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def _valid_date(date: str) -> bool:
    """形状正则 + 真实日历校验（2026-13-99 这类假日期同样 400）。"""
    if not (isinstance(date, str) and _DATE_RE.fullmatch(date)):
        return False
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _safe_file(base: Path, *parts: str):
    """拼接并校验路径落在 base 内；任一分段含穿越符 / 越界 -> 返回 None。"""
    for p in parts:
        if p in ("", ".", "..") or "/" in p or "\\" in p:
            return None
    target = (base / Path(*parts)).resolve()
    if not _within(base, target):
        return None
    return target


def _read_json(path: Path):
    """读 JSON：缺失/空 -> ('missing', None)；解析错 -> ('error', None)；成功 -> ('ok', data)。"""
    if not path.is_file() or path.stat().st_size == 0:
        return "missing", None
    try:
        with path.open("r", encoding="utf-8") as f:
            return "ok", json.load(f)
    except (json.JSONDecodeError, OSError):
        return "error", None


def _read_text(path: Path):
    if not path.is_file() or path.stat().st_size == 0:
        return "missing", None
    try:
        return "ok", path.read_text(encoding="utf-8")
    except OSError:
        return "error", None


def _not_found(label: str):
    # 文件缺失/空：返回 200 + status=error 信封（优雅降级，绝不 500）
    return fail(message=f"数据文件缺失或为空：{label}", code="not_found", http_status=200)


def _serve_whitelist_json(key: str, label: str):
    status, data = _read_json(_FILE_WHITELIST[key])
    if status == "ok":
        return ok(data=data, message=label)
    if status == "error":
        return fail(message=f"{label} 解析失败", code="invalid_data", http_status=200)
    return _not_found(label)


def _serve_recommendation_gated(key: str, label: str):
    """每日荐股：白名单 JSON 透传 + 输出边界二道闸（T-245）。

    上游 generate_daily_recommendation 已在 apply_risk_gate 踢出 overall_level==high，
    此处再闸一次：防御陈旧/截断 JSON 或旁路写入把高危标的重新带入推荐。
    被剔除项不静默——在信封 message 注明剔除数，供前端显著提示。
    unknown≠guilty：仅剔除已确认 high，not_scanned/unknown/low/medium 一律保留。
    """
    status, data = _read_json(_FILE_WHITELIST[key])
    if status != "ok" or not isinstance(data, dict):
        return _serve_whitelist_json(key, label)
    picks = data.get("picks")
    if not isinstance(picks, list):
        return ok(data=data, message=label)
    kept, dropped = [], 0
    for p in picks:
        rs = p.get("risk_scan") if isinstance(p, dict) else None
        if isinstance(rs, dict) and rs.get("overall_level") == _RISK_HIGH:
            dropped += 1
            continue
        kept.append(p)
    if dropped:
        data = {**data, "picks": kept, "risk_gate_boundary_dropped": dropped}
        return ok(data=data, message=f"{label}（输出边界二道闸剔除 {dropped} 只高危标的）")
    return ok(data=data, message=label)


def _serve_whitelist_text(key: str, label: str):
    status, data = _read_text(_FILE_WHITELIST[key])
    if status == "ok":
        return ok(data=data, message=label)
    if status == "error":
        return fail(message=f"{label} 读取失败", code="invalid_data", http_status=200)
    return _not_found(label)


def _sanitize(obj):
    """递归把 NaN/Inf 转 None，确保产出合法 JSON（浏览器 JSON.parse 拒收 NaN/Infinity）。

    部分本地数据（如 shepherd_history.json）可能含 NaN，聚合/透传前必须清洗，
    否则前端 fetch().json() 会抛 SyntaxError 静默崩页。
    """
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


# ───────────────────────── 固定白名单文件端点 ─────────────────────────
@bp.get("/daily-snapshot")
@jwt_required
def daily_snapshot():
    """今日决策快照（data/daily_snapshot.json）—— 90/98/54 页的「今日」单一真理源。"""
    return _serve_whitelist_json("daily_snapshot", "daily_snapshot.json")


@bp.get("/daily-recommendation")
@jwt_required
def daily_recommendation():
    """每日荐股（data/daily_recommendation.json）—— 36 页主体数据源；输出边界二道闸剔除高危。"""
    return _serve_recommendation_gated("daily_recommendation", "daily_recommendation.json")


@bp.get("/user-dashboard")
@jwt_required
def user_dashboard():
    """自定义看板偏好（data/user_dashboard.json）—— 73 页本地偏好。"""
    return _serve_whitelist_json("user_dashboard", "user_dashboard.json")


@bp.get("/alert-rules")
@jwt_required
def alert_rules():
    """告警规则（data/alert_rules.json）—— 74 页规则配置。"""
    return _serve_whitelist_json("alert_rules", "alert_rules.json")


@bp.get("/alert-log")
@jwt_required
def alert_log():
    """告警触发日志（data/alerts.log）—— 74 页写入的日志原文。"""
    return _serve_whitelist_text("alert_log", "alerts.log")


@bp.get("/virtual-users-sim")
@jwt_required
def virtual_users_sim():
    """虚拟用户蒙特卡洛模拟统计（reports/virtual_users_sim.json）—— 36 页历史模拟段。

    注：落在 reports/（非 data/），因是 36 页真实读取的唯一本地文件，故作为
    固定白名单扩展根纳入，路径写死、无用户注入，安全等价。
    """
    return _serve_whitelist_json("virtual_users_sim", "virtual_users_sim.json")


# ───────────────────────── P1 量化信号（目录）─────────────────────────
@bp.get("/p1-signals")
@jwt_required
def p1_signals():
    """P1 量化信号（data/p1_signals/signal_*.json）—— 54/51 页多头侧灰度参考。

    返回 {文件名: 解析后的信号 dict}；目录缺失 -> not_found(200)，目录存在但无信号
    -> ok(data={})（与页面「未找到 P1 信号文件」的诚实语义一致）。
    """
    d = _DATA_DIR / "p1_signals"
    if not d.is_dir():
        return _not_found("p1_signals/")
    out: dict[str, object] = {}
    for fp in sorted(d.glob("signal_*.json")):
        status, data = _read_json(fp)
        if status == "ok":
            out[fp.name] = data
    return ok(data=out, message="p1_signals/")


# ───────────────────────── 决策回放归档（参数化）─────────────────────────
@bp.get("/snapshot-dates")
@jwt_required
def snapshot_dates():
    """可回放归档日期清单（data/snapshots/*.json 的日期名）—— 97 页下拉源。"""
    d = _DATA_DIR / "snapshots"
    if not d.is_dir():
        return ok(data=[], message="snapshots/ 为空")
    dates = sorted(p.stem for p in d.glob("*.json") if _DATE_RE.fullmatch(p.stem))
    return ok(data=dates, message="snapshots/")


@bp.get("/snapshot/<date>")
@jwt_required
def snapshot_by_date(date: str):
    """指定日期归档快照（data/snapshots/<date>.json）—— 97 页回放主体。"""
    if not _valid_date(date or ""):
        return fail(message="日期格式非法（须为真实 YYYY-MM-DD）", code="validation_error", http_status=400)
    path = _safe_file(_DATA_DIR / "snapshots", f"{date}.json")
    if path is None:
        return fail(message="非法路径", code="validation_error", http_status=400)
    status, data = _read_json(path)
    if status == "ok":
        return ok(data=data, message=f"snapshot {date}")
    if status == "error":
        return fail(message=f"snapshot {date} 解析失败", code="invalid_data", http_status=200)
    return _not_found(f"snapshots/{date}.json")


# ───────────────────────── 模拟交易账本（参数化）─────────────────────────
@bp.get("/paper-trades")
@jwt_required
def paper_trades():
    """指定用户模拟账本（data/paper_<user>.json）—— 42 页按用户持久化账本。"""
    user = (request.args.get("user") or "").strip()
    if not _USER_RE.fullmatch(user):
        return fail(message="user 非法（仅允许字母/数字/下划线，≤64）", code="validation_error", http_status=400)
    path = _safe_file(_DATA_DIR, f"paper_{user}.json")
    if path is None:
        return fail(message="非法路径", code="validation_error", http_status=400)
    status, data = _read_json(path)
    if status == "ok":
        return ok(data=data, message=f"paper_{user}.json")
    if status == "error":
        return fail(message=f"paper_{user}.json 解析失败", code="invalid_data", http_status=200)
    return _not_found(f"paper_{user}.json")


# ───────────────────────── 复盘笔记（参数化）─────────────────────────
@bp.get("/review-notes")
@jwt_required
def review_notes():
    """指定日期复盘笔记（data/review_notes_<date>.md）—— 51 页复盘段原文。"""
    date = (request.args.get("date") or "").strip()
    if not _valid_date(date):
        return fail(message="date 非法（须为真实 YYYY-MM-DD）", code="validation_error", http_status=400)
    path = _safe_file(_DATA_DIR, f"review_notes_{date}.md")
    if path is None:
        return fail(message="非法路径", code="validation_error", http_status=400)
    status, text = _read_text(path)
    if status == "ok":
        return ok(data={"date": date, "content": text}, message=f"review_notes_{date}.md")
    if status == "error":
        return fail(message=f"review_notes_{date}.md 读取失败", code="invalid_data", http_status=200)
    return _not_found(f"review_notes_{date}.md")


# ───────────────────────── 网页作品集（目录，扩展允许根 webapps/）─────────────────────────
@bp.get("/webapps")
@jwt_required
def webapps():
    """网页作品集元数据（webapps/*/meta.json）—— 86 页作品清单。

    路径由代码 glob 固定构造，无用户输入，杜绝穿越；返回的 meta 由页面既有的
    防御逻辑（entry 不得含 ..、不得绝对路径）在消费端二次校验。
    """
    if not _WEBAPPS_DIR.is_dir():
        return ok(data=[], message="webapps/ 为空")
    works: list[dict] = []
    for meta_path in sorted(_WEBAPPS_DIR.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 损坏 meta 跳过，不渲染半残卡片
            continue
        if not isinstance(meta, dict):
            continue
        entry = meta.get("entry")
        if not (isinstance(meta.get("title"), str) and meta.get("title").strip()):
            continue
        if not (isinstance(entry, str) and entry.strip() and ".." not in entry
                and not entry.startswith(("/", "\\"))):
            continue
        works.append({
            "dir": meta_path.parent.name,
            "title": str(meta.get("title")).strip(),
            "desc": str(meta.get("desc") or "").strip(),
            "entry": entry.strip(),
            "version": str(meta.get("version", "—")),
            "added": str(meta.get("added", "—")),
        })
    return ok(data=works, message="webapps/")


# ───────────────────────── 广度时序（聚合 snapshots）─────────────────────────
@bp.get("/breadth-timeseries")
@jwt_required
def breadth_timeseries():
    """广度时序（data/snapshots/*.json 聚合）—— W3 广度·温度页时序图表源。

    每个 snapshot 含 indicators{up_count,down_count,limit_up,limit_down,red_ratio,
    median_chg} + 顶层 temperature；聚合为按日期升序的时序数组。路径由代码 glob 构造，
    无用户注入，安全等价白名单；目录缺失 -> ok(data=[])。
    """
    d = _DATA_DIR / "snapshots"
    if not d.is_dir():
        return ok(data=[], message="snapshots/ 为空")
    series: list[dict] = []
    for fp in sorted(d.glob("*.json")):
        if not _DATE_RE.fullmatch(fp.stem):
            continue
        status, rec = _read_json(fp)
        if status != "ok" or not isinstance(rec, dict):
            continue
        ind = rec.get("indicators") or {}
        series.append({
            "date": rec.get("date") or fp.stem,
            "temperature": rec.get("temperature"),
            "up_count": ind.get("up_count"),
            "down_count": ind.get("down_count"),
            "limit_up": ind.get("limit_up"),
            "limit_down": ind.get("limit_down"),
            "red_ratio": ind.get("red_ratio"),
            "median_chg": ind.get("median_chg"),
        })
    series.sort(key=lambda r: str(r["date"]))
    return ok(data=_sanitize(series), message="breadth-timeseries")


# ───────────────────────── 连板梯队明细（固定文件）─────────────────────────
# 与白名单同款固定绝对路径、无用户注入，安全等价。
_FILE_WHITELIST["ladder_detail"] = _DATA_DIR / "shepherd_ladder_history.json"


@bp.get("/ladder-detail")
@jwt_required
def ladder_detail():
    """连板梯队历史明细（data/shepherd_ladder_history.json）—— W3 连板共振页数据源。

    结构 {日期: {date, distribution{连板数:家数}, max_boards, total_connect, updated_at,
    [suspect?]}}；归一化为按日期升序数组返回，便于前端画板位分布+趋势。
    文件缺失 -> not_found(200)。
    """
    status, data = _read_json(_FILE_WHITELIST["ladder_detail"])
    if status == "ok":
        rows: list[dict] = []
        if isinstance(data, dict):
            for day in sorted(data.keys()):
                rec = data[day] if isinstance(data[day], dict) else {}
                rows.append({
                    "date": rec.get("date") or day,
                    "distribution": rec.get("distribution") or {},
                    "max_boards": rec.get("max_boards"),
                    "total_connect": rec.get("total_connect"),
                    "updated_at": rec.get("updated_at"),
                    "suspect": rec.get("suspect"),
                })
        return ok(data=_sanitize(rows), message="ladder-detail")
    if status == "error":
        return fail(message="shepherd_ladder_history.json 解析失败", code="invalid_data", http_status=200)
    return _not_found("shepherd_ladder_history.json")


# ───────────────────────── 长周期广度历史（固定文件）─────────────────────────
# 与白名单同款固定绝对路径、无用户注入，安全等价。
_FILE_WHITELIST["breadth_history"] = _DATA_DIR / "shepherd_history.json"


@bp.get("/breadth-history")
@jwt_required
def breadth_history():
    """长周期广度历史（data/shepherd_history.json）—— W3 广度·温度页长周期时序源。

    真实文件为 2007→2026 的逐日广度数组（含 up_count/down_count/limit_up/limit_down/
    red_ratio/connect_hl/zt_fail_ratio/zt_prev_ret 等，个别字段为 NaN）。读取后递归清洗
    NaN/Inf 为 None（浏览器 JSON.parse 拒收 NaN），返回干净数组；缺失 -> not_found(200)。
    """
    status, data = _read_json(_FILE_WHITELIST["breadth_history"])
    if status == "ok":
        if not isinstance(data, list):
            data = data.get("data", []) if isinstance(data, dict) else []
        return ok(data=_sanitize(data), message="breadth-history")
    if status == "error":
        return fail(message="shepherd_history.json 解析失败", code="invalid_data", http_status=200)
    return _not_found("shepherd_history.json")


# ───────────────────────── W3 后续簇（5 个真实本地数据源）─────────────────────────
# 与白名单同款固定绝对路径、无用户注入，安全等价。字段名经 2026-11-07 真扫确认，
# 绝不臆造；所有响应统一递归清洗 NaN/Inf（浏览器 JSON.parse 拒收裸 NaN）。
_FILE_WHITELIST["event_pool"] = _DATA_DIR / "event_pool_brief.json"
_FILE_WHITELIST["prediction_log"] = _DATA_DIR / "prediction_log.json"
_FILE_WHITELIST["p1_sync_status"] = _DATA_DIR / "p1_sync_status.json"
_FILE_WHITELIST["backtest_runs"] = _DATA_DIR / "backtest_runs.json"
_FILE_WHITELIST["data_refresh_state"] = _DATA_DIR / "data_refresh_state.json"


def _strip_sensitive(obj, banned_keys=None):
    """递归剔除敏感 key，防本机绝对路径随响应泄露。

    p1_sync_status.json 含多类部署环境绝对路径：target_dir（同步目标目录）、
    health.signal_dir（信号目录）、health.status_file（状态文件）——三者都泄露
    'E:\\\\...\\\\data\\\\...' 本机部署路径，均不应出现在浏览器可见的 API 响应里。
    默认一并剔除；嵌套在 dict / list 内的同名 key 也递归清除。该函数只删 key，
    不改写任何值。
    """
    banned = banned_keys or {"target_dir", "signal_dir", "status_file"}
    if isinstance(obj, dict):
        return {k: _strip_sensitive(v, banned) for k, v in obj.items() if k not in banned}
    if isinstance(obj, (list, tuple)):
        return [_strip_sensitive(v, banned) for v in obj]
    return obj


def _serve_json_sanitized(key: str, label: str, strip_sensitive: bool = False):
    """读固定白名单 JSON → 可选递归脱敏 → 清洗 NaN/Inf → 统一信封。"""
    status, data = _read_json(_FILE_WHITELIST[key])
    if status == "ok":
        if strip_sensitive:
            data = _strip_sensitive(data)
        return ok(data=_sanitize(data), message=label)
    if status == "error":
        return fail(message=f"{label} 解析失败", code="invalid_data", http_status=200)
    return _not_found(label)


@bp.get("/event-pool")
@jwt_required
def event_pool():
    """事件因子池（data/event_pool_brief.json）—— W3 事件因子页。

    结构 {date, model, source, note, count, pool[{rank,symbol,score,raw_rank,
    raw_pred,signal,source}]}。note 是「统计意义上的超额收益概率排序，非买卖指令」，
    端点原样透出，前端必须原样展示，不得包装成荐股。
    """
    return _serve_json_sanitized("event_pool", "event_pool_brief.json")


@bp.get("/prediction-log")
@jwt_required
def prediction_log():
    """决策预测校准日志（data/prediction_log.json）—— W3 预测校准页。

    真实文件为 32 行逐日数组；hit / realized 可为 null（尚未兑现），
    端点原样保留 null，不补 0 / false。顶层非 list 时归一为 []（同 breadth_history）。
    """
    status, data = _read_json(_FILE_WHITELIST["prediction_log"])
    if status == "ok":
        if not isinstance(data, list):
            data = data.get("data", []) if isinstance(data, dict) else []
        return ok(data=_sanitize(data), message="prediction-log")
    if status == "error":
        return fail(message="prediction_log.json 解析失败", code="invalid_data", http_status=200)
    return _not_found("prediction_log.json")


@bp.get("/p1-sync-status")
@jwt_required
def p1_sync_status():
    """P1 信号同步状态（data/p1_sync_status.json）—— W3 运维页。

    ⚠️ 原始文件含 target_dir 绝对路径，响应经 _strip_sensitive 递归剔除，
    包括嵌套在 health.rows[] 等容器内的同名 key，防部署路径泄露。
    """
    return _serve_json_sanitized("p1_sync_status", "p1_sync_status.json", strip_sensitive=True)


@bp.get("/backtest-runs")
@jwt_required
def backtest_runs():
    """回测运行记录（data/backtest_runs.json）—— W3 运维页。

    结构 {runs:[{run_id, created_at, status, params, summary}]}。
    ⚠️ total_return_pct / sharpe_ratio 可为负，端点原样透出，不取绝对值、不做平滑。
    """
    return _serve_json_sanitized("backtest_runs", "backtest_runs.json")


@bp.get("/data-refresh-state")
@jwt_required
def data_refresh_state():
    """数据刷新状态（data/data_refresh_state.json）—— W3 运维页。

    结构 {attempts_today, last_run_date, last_result, finished_at,
    last_csv_date, detail}；detail 为刷新脚本原始输出，原样透出不美化。
    """
    return _serve_json_sanitized("data_refresh_state", "data_refresh_state.json")


# ───────────────────────── 六维量化评分（W4-A，逐维独立取数/独立降级）─────────────────────────
# 契约：GET /api/v2/read/six-dim?code=600519（@jwt_required）
# 评分纯逻辑 modules.six_dim.compute_dims：六维等权、缺维为 None 且不参与 overall 平均。
# 三个取数源彼此独立、各自 try/except 降级；任一源失败只让对应维为 None，
# 绝不补 0 / 编造 / 用 now() 当权威数据日兜底。
_DIM_ORDER = ("technical", "capital", "value", "growth", "fundamental", "cycle")
_SIX_DIM_NOTE = "逐维独立取数、独立降级；缺失维为 null 且不参与 overall 平均"
# compute_dims 的 fetch_spot 期望中文键：换手率/量比/市盈率-动态/市净率
# （six_dim.py:195-204 写死，禁止臆造；akshare 快照按其列名原样透出）


def _six_dim_hist(code: str):
    """历史日线（近 ~400 自然日）：get_fetcher().get_kline(code, start, None, 'daily', 'qfq')。

    失败/空 -> None（技术/周期维缺失）。已核实：get_kline(period='daily') 实际走
    get_daily()，返回的是英文列 date/close/...（fetcher_kline.py:334-338），而
    compute_dims 要求 fetch_hist 含中文「收盘」列（six_dim.py:166）——故在此把
    close 适配为「收盘」（仅列名映射，不改数值、不补 0）。start 仅用于框定查询
    窗口，不是权威数据日；data 的 date 必须来自 K 线最后一根。
    """
    try:
        from ..api.market_routes import get_fetcher
        start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        df = get_fetcher().get_kline(code, start, None, "daily", "qfq")
    except Exception:  # noqa: BLE001 - 取数失败仅让技术/周期维缺失，不 500
        return None
    if df is None or len(df) == 0:
        return None
    if "收盘" not in df.columns and "close" in df.columns:
        df = df.rename(columns={"close": "收盘"})
    return df


def _six_dim_spot(code: str):
    """实时快照行（供资金/价值维取数）：ak.stock_zh_a_spot_em() 按「代码」筛行。

    取证留痕（2026-11-07 已核实）：get_fetcher().get_realtime_quote(code) 返回字段为
    ticker/name/open/prev_close/current/high/low/volume/amount/bid/ask/datetime，
    **不含**「换手率/量比/市盈率-动态/市净率」——故此处**不调用**该实时接口：
    既删掉永不命中的死分支，也省掉每次请求白跑一次新浪实时接口（内部 10s 超时
    + 缓存兜底）的无谓网络往返。直接走 akshare 快照（与 pages/72 口径一致），按
    「代码」筛行后整行 .to_dict() 透出，字段名写死、禁止臆造。
    任一异常 / 字段取不到 -> {}（capital/value 维如实为 None，绝不补 0）。
    """
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty or "代码" not in df.columns:
            return {}
        row = df[df["代码"].astype(str) == str(code)]
        return row.iloc[0].to_dict() if len(row) else {}
    except Exception:  # noqa: BLE001 - akshare 挂掉仅让资金/价值维缺失，不 500
        return {}


def _six_dim_fin(code: str):
    """东财财务摘要（akshare stock_financial_abstract）：异常 -> None。"""
    try:
        import akshare as ak
        return ak.stock_financial_abstract(symbol=code)
    except Exception:  # noqa: BLE001 - 财务源失败仅让成长/基本面维缺失，不 500
        return None


def _six_dim_date(df):
    """K 线最后一根的权威日期（列名兼容「日期」/date，取 str(...)[:10]）。

    取不到一律 None——绝不用 datetime.now() 兜底（红线：权威数据日必须来自数据）。
    """
    if df is None or len(df) == 0:
        return None
    for col in ("日期", "date"):
        if col in df.columns:
            try:
                s = str(df[col].iloc[-1])[:10]
                return s or None
            except Exception:  # noqa: BLE001
                return None
    return None


def _six_dim_num(v):
    """raw 数值字段规范化为 float|None；NaN/Inf/非数值/None 一律 None（绝不补 0）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


@bp.get("/six-dim")
@jwt_required
def six_dim():
    """六维量化评分（技术/资金/价值/成长/基本面/周期），逐维独立取数、独立降级。

    GET /api/v2/read/six-dim?code=600519。缺失维为 null 且不参与 overall 平均；
    date 为 K 线最后一根的权威日期，取不到则 null。全响应过 _sanitize() 清洗 NaN/Inf。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"\d{6}", code or ""):
        return fail(message="code 非法（须为 6 位数字股票代码）",
                    code="invalid_param", http_status=400)

    # 三源一次并行：整批硬边界 = CALL_TIMEOUT_CAP（默认 12s，REQ_TIMEOUT 10<12），
    # 避免 hist→spot→fin 串行超时累加（最坏由几十秒收敛到 ~12s）。fetch_many 返回
    # dict{key: 值}，超时/异常项预填 None（不缺键）；各 _six_dim_* 内部另有 try/except，
    # 双层兜底。超时/未完成源一律按 None / {} 降级，绝不 500 / 补 0。
    try:
        from modules.fetch_parallel import fetch_many  # lazy：不增加模块级导入耦合
        res = fetch_many([
            ("hist", lambda: _six_dim_hist(code)),
            ("spot", lambda: _six_dim_spot(code)),
            ("fin", lambda: _six_dim_fin(code)),
        ])
    except Exception:  # noqa: BLE001 - 并发行本身异常：三源全体降级（诚实返回 null）
        res = {}
    hist = res.get("hist")
    spot = res.get("spot") or {}
    fin = res.get("fin")
    date = _six_dim_date(hist)

    from modules.six_dim import compute_dims  # 纯逻辑，lazy 以隔离新增依赖
    result, raw = compute_dims(
        code,
        lambda _c: hist,
        lambda _c: spot,
        lambda _c: fin,
        state_fn=None,  # 保守传 None：不臆造市场状态机函数名，周期维允许如实缺失
    )

    dims = result["dims"]
    missing = [k for k in _DIM_ORDER if dims.get(k) is None]
    data = {
        "code": code,
        "dims": dims,
        "overall": result["overall"],
        "coverage": 6 - len(missing),
        "missing": missing,
        "date": date,
        "raw": {
            "pe": _six_dim_num(raw.get("pe")),
            "pb": _six_dim_num(raw.get("pb")),
            "roe": _six_dim_num(raw.get("roe")),
            "profit_yoy": _six_dim_num(raw.get("profit_yoy")),
            "state": str(raw["state"]) if raw.get("state") is not None else None,
            "turnover": _six_dim_num(raw.get("turnover")),
            "vol_ratio": _six_dim_num(raw.get("vol_ratio")),
            "pos60": _six_dim_num(raw.get("pos60")),
        },
        "note": _SIX_DIM_NOTE,
    }
    return ok(data=_sanitize(data), message="six-dim")


# ───────────── W4-B 个股域实时只读端点（fundamentals / financials / stock-kline）─────────────
# 契约（team-lead 已拍板）：三页 24/21/22 全为实时联网计算、data/ 下零对应本地 JSON，
# 故沿用 W4-A six-dim 先例走「实时计算型只读 GET」。三页共同红线：
#   · @jwt_required + 统一 ok/fail 信封（code 为字符串业务码）+ _sanitize() 全响应清洗 NaN/Inf；
#   · code 用 ^\d{6}$ 校验，非法 -> fail(400, invalid_param)；limit 走 parse_limit_param；
#   · 多源一律 fetch_many([(key, lambda: fn())...])，不传自定义 max_workers/timeout，
#     整批硬边界 = CALL_TIMEOUT_CAP（默认 12s，REQ_TIMEOUT 10 < 12）；
#     超时/异常项按 None 降级，绝不 500、绝不补 0；W4-A 已实测该不变量。
#   · 任一字段取不到 -> null / []，禁止 0 / 50 /「持有」/ 中性默认等编造值；
#   · date 必须是权威数据日（K 线末根 date / 实时 quote datetime / 财报报告期），
#     取不到 -> null；禁止 datetime.now() 当数据日、禁止文件 mtime；
#     now()-400d 仅用于框定 K 线查询窗口（与 _six_dim_hist 一致），不是数据日。
#   · 测试环境 monkeypatch 下列 _w4b_* 取数源，绝不真调 akshare / 新浪 / 东财 / BaoStock。
_W4B_NOTE = "逐字段独立取数、独立降级；缺失为 null 且不补 0"
_W4B_PRICE_DOMAIN = "market"  # 22 页全页交易屏红涨绿跌口径
_W4B_REPORTS = ("income", "balance", "cash")
_W4B_PERIODS = ("daily", "weekly", "monthly")
_W4B_PERF_KEYS = (
    "revenue_yi", "revenue_yoy", "net_profit_yi", "profit_yoy",
    "gross_margin", "roe", "alr", "current_ratio", "equity_ratio",
)


def _w4b_limit(default, hi=200):
    """分页条数一律走 parse_limit_param（钳下界 1、防负数穿透）；lazy 导入以免改动
    文件顶部 import 区（既有 21 端点一字不动）。"""
    from ..utils.params import parse_limit_param
    return parse_limit_param("limit", default=default, hi=hi)


def _w4b_num(v):
    """数值字段 -> float|None；NaN/Inf/非数值/None 一律 None（绝不补 0）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def _w4b_str(v):
    """字符串字段 -> str|None；None / 空串一律 None（诚实缺失，不补占位）。"""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _w4b_basic(code):
    """get_fundamentals(code) -> dict{name,industry,price,pe_ttm,market_cap} | None。
    已核实（fetcher_fundamental.py:152-158/206-209）该接口**不返回 pb/roe**，故不臆造。"""
    try:
        from ..api.market_routes import get_fetcher
        d = get_fetcher().get_fundamentals(code)
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001 - 取数失败仅让对应字段缺失，不 500
        return None


def _w4b_spot(code):
    """实时行情 datetime（spot_date 权威来源）：get_realtime_quote(code) -> dict | None。
    get_realtime_quote 确实返回 datetime（fetcher_realtime.py:189），此处取其日期，
    与 six-dim 不同（six-dim 需要它**不含**的换手率/量比等四字段才删掉该调用）。
    全源失败时该接口回退过期缓存可能带旧 datetime —— 仍是数据自带时间戳、非 now()，
    符合红线，但可能陈旧（已在回报中如实说明）。"""
    try:
        from ..api.market_routes import get_fetcher
        d = get_fetcher().get_realtime_quote(code)
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _w4b_kline(code, period="daily"):
    """get_kline(code, start, None, period, 'qfq') -> DataFrame | None（异常/空降级）。"""
    try:
        from ..api.market_routes import get_fetcher
        start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")  # 仅查询窗口
        df = get_fetcher().get_kline(code, start, None, period, "qfq")
    except Exception:  # noqa: BLE001
        return None
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        return None
    return df


def _w4b_financial(code, report_type):
    """get_financial(code, report_type) -> DataFrame | None（异常/空降级）。
    已核实（_market_data_io.py:448-459）= ak.stock_financial_report_sina(...).head(8)，
    「行=报告期、列=中文科目」wide DataFrame，与旧页 22 财报口径同源同列名。"""
    try:
        from ..api.market_routes import get_fetcher
        df = get_fetcher().get_financial(code, report_type)
    except Exception:  # noqa: BLE001
        return None
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        return None
    return df


def _w4b_spot_date(spot):
    """实时 quote datetime -> 'YYYY-MM-DD' | None（权威数据日，取不到不兜底）。"""
    if not isinstance(spot, dict):
        return None
    v = spot.get("datetime")
    if v is None:
        return None
    s = str(v)[:10]
    return s or None


def _w4b_kline_date(df):
    """K 线最后一根 date -> 'YYYY-MM-DD' | None（兼容「日期」/date 列，绝不 now()）。"""
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        return None
    for col in ("date", "日期"):
        if col in df.columns:
            try:
                s = str(df[col].iloc[-1])[:10]
                return s or None
            except Exception:  # noqa: BLE001
                return None
    return None


def _w4b_compute_perf(inc_df, bal_df):
    """9 字段业绩指标（复用旧页 pages/22 _calc_perf :373-444 口径）。

    真源 get_financial('income'/'balance') 为「行=报告期、列=科目」wide DataFrame，
    形态可支撑；任一字段算不出 -> None（绝不补 0 / 编造）。恒返回 9 字段 dict；
    两表全失败时为全 None 字典（逐字段独立降级，非编造）。
    """
    from modules import fundamental_helpers as fh
    out = {k: None for k in _W4B_PERF_KEYS}
    inc = inc_df if hasattr(inc_df, "columns") else None
    bal = bal_df if hasattr(bal_df, "columns") else None
    rev0 = rev1 = np0 = np1 = cost0 = None
    if inc is not None and len(inc) >= 1:
        rev_c = fh._find_col(inc, {"营业总收入", "营业收入"}, ("营业总收入", "营业收入"))
        np_c = fh._find_col(inc, {"净利润", "归属母公司股东的净利润"},
                            ("净利润", "归属母公司股东的净利润"))
        cost_c = fh._find_col(inc, {"营业成本"}, ("营业成本",))
        r0 = inc.iloc[0]
        r1 = inc.iloc[1] if len(inc) >= 2 else None
        rev0 = fh._to_num(r0[rev_c]) if rev_c else None
        np0 = fh._to_num(r0[np_c]) if np_c else None
        cost0 = fh._to_num(r0[cost_c]) if cost_c else None
        rev1 = fh._to_num(r1[rev_c]) if r1 is not None and rev_c else None
        np1 = fh._to_num(r1[np_c]) if r1 is not None and np_c else None
    av = lv = eq = ca = cl = None
    if bal is not None and len(bal) >= 1:
        asset_c = fh._find_col(bal, {"资产总计", "资产合计"}, ("资产总计", "资产合计"))
        liab_c = fh._find_col(bal, {"负债合计", "负债总计"}, ("负债合计", "负债总计"))
        equity_c = fh._find_col(bal, {"所有者权益合计", "股东权益合计"},
                                ("所有者权益合计", "股东权益合计"))
        ca_c = fh._find_col(bal, {"流动资产合计"}, ("流动资产合计",))
        cl_c = fh._find_col(bal, {"流动负债合计"}, ("流动负债合计",))
        b0 = bal.iloc[0]
        av = fh._to_num(b0[asset_c]) if asset_c else None
        lv = fh._to_num(b0[liab_c]) if liab_c else None
        eq = fh._to_num(b0[equity_c]) if equity_c else None
        ca = fh._to_num(b0[ca_c]) if ca_c else None
        cl = fh._to_num(b0[cl_c]) if cl_c else None
    if rev0:
        out["revenue_yi"] = round(rev0 / 1e8, 2)
    if rev0 and rev1:
        out["revenue_yoy"] = round((rev0 - rev1) / abs(rev1) * 100, 2)
    if np0 is not None:
        out["net_profit_yi"] = round(np0 / 1e8, 2)
    if np0 is not None and np1 is not None and np1 != 0:
        out["profit_yoy"] = round((np0 - np1) / abs(np1) * 100, 2)
    if rev0 and cost0:
        out["gross_margin"] = round((rev0 - cost0) / rev0 * 100, 2)
    if av and lv:
        out["alr"] = round(lv / av * 100, 2)
    if av and eq:
        out["equity_ratio"] = round(eq / av * 100, 2)
    if ca and cl:
        out["current_ratio"] = round(ca / cl, 2)
    if np0 is not None and eq:
        out["roe"] = round(np0 / abs(eq) * 100, 2)
    for k in _W4B_PERF_KEYS:  # 计算结果若含 NaN/Inf，诚实置 None，绝不补 0
        v = out[k]
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            out[k] = None
    return out


def _w4b_financial_rows(inc, bal, cash):
    """多期财报 rows（复用旧页 pages/22 _build_financial_df :466-529 口径）。

    三表（income/balance/cash）合并为统一 DataFrame，列：报告期/标签/营业总收入/
    归母净利润/扣非净利润/每股收益/净资产收益率/销售净利率/销售毛利率/资产负债率/
    每股经营现金流 + 各 _同比/_环比。纯逻辑，仅依赖 fundamental_helpers 纯函数
    （pandas/numpy，不联网）。任一表 None -> 对应衍生列为 None（诚实逐字段降级，
    绝不补 0 / 造演示行）。返回按「报告期」倒序的 list[dict]；无法构造 -> []。
    """
    try:
        import pandas as pd
        from modules import fundamental_helpers as fh
        rev = fh._extract_metric_series(inc, ["营业总收入", "营业收入"])
        np_ = fh._extract_metric_series(inc, ["净利润", "归属母公司股东的净利润",
                                               "归属于上市公司股东的净利润"])
        np_ded = fh._extract_metric_series(inc, ["扣除非经常性损益后的净利润", "扣非净利润"])
        eps = fh._extract_metric_series(inc, ["基本每股收益", "每股收益", "稀释每股收益"])
        cost = fh._extract_metric_series(inc, ["营业成本", "营业总成本"])
        equity = fh._extract_metric_series(bal, ["所有者权益合计", "股东权益合计",
                                                  "归属于母公司所有者权益合计"])
        asset = fh._extract_metric_series(bal, ["资产总计", "资产合计"])
        liab = fh._extract_metric_series(bal, ["负债合计", "负债总计"])
        ops_cf = fh._extract_metric_series(cash, ["经营活动产生的现金流量净额",
                                                   "经营活动现金流入小计", "经营活动现金流量净额"])
        share_cap = fh._extract_metric_series(bal, ["实收资本(或股本)", "股本", "实收资本"])
        ops_cf_ps = fh._extract_metric_series(cash, ["每股经营活动产生的现金流量净额",
                                                      "每股经营现金流量"])
        all_idx = set()
        for s in (rev, np_, np_ded, eps, cost, equity, asset, liab, ops_cf, share_cap):
            if s is not None:
                all_idx.update(s.index)
        if not all_idx:
            return []
        rows = []
        for idx in sorted(all_idx):
            row = {"报告期": idx,
                   "标签": fh._period_label(idx, "年度" if idx.month == 12 else "季度")}
            r = rev.get(idx) if rev is not None else None
            n = np_.get(idx) if np_ is not None else None
            nd = np_ded.get(idx) if np_ded is not None else None
            e = eps.get(idx) if eps is not None else None
            c = cost.get(idx) if cost is not None else None
            eq = equity.get(idx) if equity is not None else None
            ast = asset.get(idx) if asset is not None else None
            lb = liab.get(idx) if liab is not None else None
            oc = ops_cf.get(idx) if ops_cf is not None else None
            sc = share_cap.get(idx) if share_cap is not None else None
            row["营业总收入"] = round(r / 1e8, 2) if r is not None else None
            row["归母净利润"] = round(n / 1e8, 2) if n is not None else None
            row["扣非净利润"] = round(nd / 1e8, 2) if nd is not None else None
            row["每股收益"] = round(e, 3) if e is not None else None
            row["净资产收益率"] = round(n / eq * 100, 2) if n is not None and eq and eq != 0 else None
            row["销售净利率"] = round(n / r * 100, 2) if n is not None and r and r != 0 else None
            row["销售毛利率"] = round((r - c) / r * 100, 2) if r is not None and c is not None and r != 0 else None
            row["资产负债率"] = round(lb / ast * 100, 2) if lb is not None and ast and ast != 0 else None
            if oc is not None and sc is not None and sc != 0:
                row["每股经营现金流"] = round(oc / sc, 3)
            elif ops_cf_ps is not None:
                row["每股经营现金流"] = ops_cf_ps.get(idx)
            else:
                row["每股经营现金流"] = None
            rows.append(row)
        df = pd.DataFrame(rows)
        if df.empty:
            return []
        numeric_cols = ["营业总收入", "归母净利润", "扣非净利润", "每股收益",
                        "净资产收益率", "销售净利率", "销售毛利率", "每股经营现金流"]
        for col in numeric_cols:  # None -> NaN，避免 _compute_yoy/qoq 对 None 做减法抛异常
            df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in numeric_cols:
            s = df.set_index("报告期")[col]
            df[f"{col}_同比"] = df["报告期"].map(fh._compute_yoy(s).to_dict())
            df[f"{col}_环比"] = df["报告期"].map(fh._compute_qoq(s).to_dict())
        df["报告期"] = df["报告期"].apply(lambda x: str(x)[:10])
        df = df.sort_values("报告期", ascending=False).reset_index(drop=True)
        return df.to_dict(orient="records")
    except Exception:  # noqa: BLE001 - 任一构造异常一律诚实返回 []，绝不 500 / 造演示行
        return []


def _w4b_kline_rows(df, limit):
    """K 线 rows：按 date 升序、tail(limit)，英文列原样透出；返回 (rows, date)。
    rows 的 date 统一 'YYYY-MM-DD'；date = 最后一根权威数据日，空则 None（绝不 now()）。"""
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        return [], None
    if "date" not in df.columns:
        return [], None
    try:
        d = df.copy().sort_values("date")
        last = str(d["date"].iloc[-1])[:10] or None
        d = d.tail(limit).copy()
        d["date"] = d["date"].apply(lambda x: str(x)[:10])
        return d.to_dict(orient="records"), last
    except Exception:  # noqa: BLE001
        return [], None


@bp.get("/fundamentals")
@jwt_required
def fundamentals():
    """基本面五字段 + 双日期 + 9 字段 perf（逐字段独立取数 / 独立降级）。

    GET /api/v2/read/fundamentals?code=600519。date = spot_date（实时 quote datetime），
    spot 取不到则 date=null，kline_date 不顶替。perf 真源 get_financial income/balance。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"\d{6}", code or ""):
        return fail(message="code 非法（须为 6 位数字股票代码）",
                    code="invalid_param", http_status=400)
    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([
            ("basic", lambda: _w4b_basic(code)),
            ("spot", lambda: _w4b_spot(code)),
            ("kline", lambda: _w4b_kline(code, "daily")),
            ("income", lambda: _w4b_financial(code, "income")),
            ("balance", lambda: _w4b_financial(code, "balance")),
        ])
    except Exception:  # noqa: BLE001 - 并发行本身异常：五源全体降级（诚实返回 null）
        res = {}
    basic = res.get("basic") or {}
    spot_date = _w4b_spot_date(res.get("spot"))
    kline_date = _w4b_kline_date(res.get("kline"))
    perf = _w4b_compute_perf(res.get("income"), res.get("balance"))
    data = {
        "code": code,
        "name": _w4b_str(basic.get("name")),
        "industry": _w4b_str(basic.get("industry")),
        "price": _w4b_num(basic.get("price")),
        "pe_ttm": _w4b_num(basic.get("pe_ttm")),
        "market_cap": _w4b_num(basic.get("market_cap")),
        "spot_date": spot_date,
        "kline_date": kline_date,
        "perf": perf,
        "priceDomain": _W4B_PRICE_DOMAIN,
        "date": spot_date,  # 明确取 spot_date；spot 缺失则 null，不用 kline_date 顶替
        "note": _W4B_NOTE,
    }
    return ok(data=_sanitize(data), message="fundamentals")


@bp.get("/financials")
@jwt_required
def financials():
    """多期财报 rows（三表合并，旧页 _build_financial_df 口径），按报告期倒序、limit 截断。

    GET /api/v2/read/financials?code=600519&report=income&limit=8。
    report 校验 ∈{income,balance,cash} 并回显；rows 列名与旧页一致，取不到 -> []，
    date = rows 最新「报告期」，空则 null。绝不造演示行。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"\d{6}", code or ""):
        return fail(message="code 非法（须为 6 位数字股票代码）",
                    code="invalid_param", http_status=400)
    report = (request.args.get("report") or "income").strip().lower()
    if report not in _W4B_REPORTS:
        return fail(message="report 非法（须为 income/balance/cash）",
                    code="invalid_param", http_status=400)
    limit = _w4b_limit(8)
    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([
            ("income", lambda: _w4b_financial(code, "income")),
            ("balance", lambda: _w4b_financial(code, "balance")),
            ("cash", lambda: _w4b_financial(code, "cash")),
        ])
    except Exception:  # noqa: BLE001
        res = {}
    rows = _w4b_financial_rows(res.get("income"), res.get("balance"), res.get("cash"))[:limit]
    date = rows[0]["报告期"] if rows else None
    data = {"code": code, "report": report, "rows": rows, "date": date, "note": _W4B_NOTE}
    return ok(data=_sanitize(data), message="financials")


@bp.get("/stock-kline")
@jwt_required
def stock_kline():
    """个股 K 线（过 _sanitize 修复 /api/kline 的 NaN 裸奔风险），英文列原样透出。

    GET /api/v2/read/stock-kline?code=600519&period=daily&limit=120。
    rows 按 date 升序、tail(limit)；date = 最后一根权威数据日，空则 null（绝不 now()）。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"\d{6}", code or ""):
        return fail(message="code 非法（须为 6 位数字股票代码）",
                    code="invalid_param", http_status=400)
    period = (request.args.get("period") or "daily").strip().lower()
    if period not in _W4B_PERIODS:
        return fail(message="period 非法（须为 daily/weekly/monthly）",
                    code="invalid_param", http_status=400)
    limit = _w4b_limit(120)
    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([("kline", lambda: _w4b_kline(code, period))])
    except Exception:  # noqa: BLE001
        res = {}
    rows, date = _w4b_kline_rows(res.get("kline"), limit)
    data = {"code": code, "period": period, "rows": rows, "date": date, "note": _W4B_NOTE}
    return ok(data=_sanitize(data), message="stock-kline")


# ───────────── W4-C 个股对比/深度/分时只读端点（compare-one / research-deep / stock-intraday）─────────────
# 契约（与 W4-B 同款红线，team-lead 已确认）：三端点均为实时联网计算、data/ 下零对应本地 JSON，
# 沿用 W4-A/W4-B 先例走「实时计算型只读 GET」。三端点共同红线：
#   · @jwt_required + 统一 ok/fail 信封；code 用 ^\d{6}$ 校验，非法 -> fail(400, invalid_param)；
#   · 多源一律 fetch_many([(key, lambda: fn())...])，不传自定义 max_workers/timeout
#     （整批硬边界 = CALL_TIMEOUT_CAP，默认 12s）；超时/异常项按 None 降级，绝不 500、绝不补 0；
#   · 任一字段取不到 -> null / []，禁止 0 / 50 /「持有」/ 中性默认等编造值；
#   · date 必须是权威数据日（K 线末根 date / 实时 quote datetime / 分时 trade_date），
#     取不到 -> null；禁止 datetime.now() 当数据日、禁止文件 mtime；
#   · 测试环境 monkeypatch 下列 _w4b_* / _w4c_* 取数源，绝不真调 akshare / 新浪 / 东财 / BaoStock。
# 字段名清单（31 个行情/技术/评分字段）本应来自 modules.compare.py，但经核对该模块**无** _NUM_FIELDS
# 常量；真正的 31 字段名清单定义在 modules.stock_research._NUM_FIELDS（stock_research.py:440）。
# 此处仅「借用字段名清单」，绝不复制 compare.py 的 0 填充 / now() 兜底 / 补值逻辑。
_W4C_NOTE = "逐字段独立取数、独立降级；缺失为 null 且不补 0"
# 31 字段名（来源：modules.stock_research._NUM_FIELDS，行情/技术/评分混合，扁平顶层级返回）
_W4C_COMPARE_FIELDS = (
    "current_price", "prev_close", "change_pct", "entry_price", "target_price",
    "stop_price", "atr14", "support", "resistance", "lo52", "hi52",
    "ma5v", "ma10v", "ma20v", "trapped", "vol_now", "vol_avg", "vol_chg",
    "q_open", "q_high", "q_low", "q_prev", "tech_score", "news_score",
    "macro_score", "vol_score", "sector_score", "composite", "pos_pct",
    "neg_pct", "pos52",
)
assert len(_W4C_COMPARE_FIELDS) == 31, "W4-C compare-one 字段名清单必须为 31 个"


def _w4c_compare_metrics(basic, spot, kline):
    """compare-one 的 31 字段逐字段独立计算；取不到 -> None（绝不补 0）。

    可复用源（_w4b_basic/_w4b_spot/_w4b_kline）能直接/派生出的字段如实计算；
    其余字段（entry_price/target_price/stop_price/atr14/trapped/q_*/news_score/
    macro_score/sector_score/pos_*/composite/tech_score 等依赖分析引擎、本端点
    不接入）一律诚实为 None。K 线派生量：prev_close/change_pct/support/resistance/
    lo52/hi52/ma5v/ma10v/ma20v/vol_now/vol_avg/vol_chg。
    """
    basic = basic if isinstance(basic, dict) else {}
    spot = spot if isinstance(spot, dict) else {}
    kdf = kline if hasattr(kline, "columns") and len(kline) else None
    out = {f: None for f in _W4C_COMPARE_FIELDS}
    # current_price：优先 basic.price（实时价）；basic 缺失再退 spot.current
    if basic.get("price") is not None:
        out["current_price"] = _w4b_num(basic.get("price"))
    else:
        out["current_price"] = _w4b_num(spot.get("current"))
    if kdf is None:
        return out
    try:
        last = kdf.iloc[-1]
        n = len(kdf)
        prev = kdf.iloc[-1 - 1] if n >= 2 else None  # 倒数第二根（前收）
        if prev is not None:
            pc = _w4b_num(prev.get("close"))
            if pc is not None:
                out["prev_close"] = pc
                lc = _w4b_num(last.get("close"))
                if lc is not None:
                    out["change_pct"] = round((lc - pc) / pc * 100, 2)
        win = kdf.tail(60)
        out["support"] = _w4b_num(win["low"].min())
        out["resistance"] = _w4b_num(win["high"].max())
        out["lo52"] = _w4b_num(kdf["low"].min())   # 全样本最低（52 周代理，诚实不编造）
        out["hi52"] = _w4b_num(kdf["high"].max())
        vol = kdf["volume"]
        out["ma5v"] = _w4b_num(vol.tail(5).mean())
        out["ma10v"] = _w4b_num(vol.tail(10).mean())
        out["ma20v"] = _w4b_num(vol.tail(20).mean())
        out["vol_now"] = _w4b_num(last.get("volume"))
        avg = _w4b_num(vol.tail(60).mean())
        out["vol_avg"] = avg
        vn = out["vol_now"]
        if avg not in (None, 0) and vn is not None:
            out["vol_chg"] = round((vn - avg) / avg * 100, 2)
    except Exception as e:  # noqa: BLE001 - 算错即该组字段保持 None，绝不编造
        logging.getLogger(__name__).debug("成交量派生计算失败，相关字段保持 None: %s", e)
    return out


def _w4c_deep_tech(kline):
    """research-deep 技术面（由 kline 算）：ma5/ma10/ma20/ma60、amplitude；算不出 -> None。

    turnover（换手率）需流通股本，kline 无此源 -> 诚实为 None；pb 由 get_fundamentals
    不返回（_w4b_basic 已核实）-> 由端点置 None。
    """
    out = {"ma5": None, "ma10": None, "ma20": None, "ma60": None, "amplitude": None}
    kdf = kline if hasattr(kline, "columns") and len(kline) else None
    if kdf is None:
        return out
    try:
        close = kdf["close"]
        for k, w in (("ma5", 5), ("ma10", 10), ("ma20", 20), ("ma60", 60)):
            if len(kdf) >= w:
                out[k] = _w4b_num(close.tail(w).mean())
        n = len(kdf)
        if n >= 2:
            pc = _w4b_num(kdf.iloc[-2].get("close"))
            if pc not in (None, 0):
                hi = _w4b_num(kdf.iloc[-1].get("high"))
                lo = _w4b_num(kdf.iloc[-1].get("low"))
                if hi is not None and lo is not None:
                    out["amplitude"] = round((hi - lo) / pc * 100, 2)
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).debug("技术面派生计算失败，相关字段保持 None: %s", e)
    return out


def _w4c_intraday(code):
    """stock-intraday 底层 fetcher：get_fetcher().get_stock_intraday_sina(code)
    -> (df, prev_close, trade_date) 或 (None, None, None)。异常 -> (None,None,None)（绝不 500）。

    已核实（fetcher_realtime.py:412）：新浪分钟 K 线，返回 DataFrame[time,open,high,low,
    close,volume,amount] + 前收 + 交易日；本环境下是唯一的个股分时来源。
    """
    try:
        from ..api.market_routes import get_fetcher
        return get_fetcher().get_stock_intraday_sina(code)
    except Exception:  # noqa: BLE001
        return None, None, None


@bp.get("/compare-one")
@jwt_required
def compare_one():
    """单股粒度对比（31 字段扁平顶层级），逐字段独立取数、独立降级。

    GET /api/v2/read/compare-one?code=600519&period=daily。复用 _w4b_basic/_w4b_spot/
    _w4b_kline 已验证助手；date = K 线末根 date 或 spot datetime（取不到 null，绝不 now()）。
    字段取不到一律 null，禁止补 0。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"\d{6}", code or ""):
        return fail(message="code 非法（须为 6 位数字股票代码）",
                    code="invalid_param", http_status=400)
    period = (request.args.get("period") or "daily").strip().lower()
    if period not in _W4B_PERIODS:
        return fail(message="period 非法（须为 daily/weekly/monthly）",
                    code="invalid_param", http_status=400)
    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([
            ("basic", lambda: _w4b_basic(code)),
            ("spot", lambda: _w4b_spot(code)),
            ("kline", lambda: _w4b_kline(code, period)),
        ])
    except Exception:  # noqa: BLE001 - 并发行异常：三源全体降级（诚实返回 null）
        res = {}
    basic = res.get("basic")
    spot = res.get("spot")
    kline = res.get("kline")
    bdict = basic if isinstance(basic, dict) else {}
    fields = _w4c_compare_metrics(basic, spot, kline)
    date = _w4b_kline_date(kline) or _w4b_spot_date(spot)
    data = {
        "code": code,
        "name": _w4b_str(bdict.get("name")),
        "industry": _w4b_str(bdict.get("industry")),
        "period": period,
        "date": date,
        **fields,
        "note": _W4C_NOTE,
    }
    return ok(data=_sanitize(data), message="compare-one")


@bp.get("/research-deep")
@jwt_required
def research_deep():
    """24 页 deep 子视图的轻量同步技术面（price/pe_ttm/pb/market_cap + 技术字段）。

    GET /api/v2/read/research-deep?code=600519。复用 _w4b_basic/_w4b_spot/_w4b_kline/
    _w4b_financial；pb 无源->null、turnover（换手率，需流通股本）无源->null。
    旧 24 页 56 键 analysis_engine 异步深度分析**本轮不接入**，deep_analysis_available
    诚实标注为 false（前端据实展示豁免卡，不造假）。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"\d{6}", code or ""):
        return fail(message="code 非法（须为 6 位数字股票代码）",
                    code="invalid_param", http_status=400)
    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([
            ("basic", lambda: _w4b_basic(code)),
            ("spot", lambda: _w4b_spot(code)),
            ("kline", lambda: _w4b_kline(code, "daily")),
            # 复用 _w4b_financial（按契约命名接入），但本轮 pb/market_cap 已可由 basic 提供、
            # financial 三表无 pb 估值，故其输出不消费、不编造；异常按 None 降级。
            ("financial", lambda: _w4b_financial(code, "income")),
        ])
    except Exception:  # noqa: BLE001
        res = {}
    basic = res.get("basic")
    spot = res.get("spot")
    kline = res.get("kline")
    bdict = basic if isinstance(basic, dict) else {}
    tech = _w4c_deep_tech(kline)
    date = _w4b_kline_date(kline) or _w4b_spot_date(spot)
    data = {
        "code": code,
        "name": _w4b_str(bdict.get("name")),
        "industry": _w4b_str(bdict.get("industry")),
        "date": date,
        "price": _w4b_num(bdict.get("price")),
        "pe_ttm": _w4b_num(bdict.get("pe_ttm")),
        "pb": None,  # get_fundamentals 不返回 pb（_w4b_basic 已核实），诚实 null
        "market_cap": _w4b_num(bdict.get("market_cap")),
        "ma5": tech.get("ma5"),
        "ma10": tech.get("ma10"),
        "ma20": tech.get("ma20"),
        "ma60": tech.get("ma60"),
        "amplitude": tech.get("amplitude"),
        "turnover": None,  # 换手率需流通股本，kline 无此源，诚实 null
        "deep_analysis_available": False,
        "note": _W4C_NOTE + "；24页异步深度分析本轮不接入（deep_analysis_available=false），前端据实展示豁免卡，不造假",
    }
    return ok(data=_sanitize(data), message="research-deep")


@bp.get("/stock-intraday")
@jwt_required
def stock_intraday():
    """个股分时薄封装（复用底层 get_stock_intraday_sina 新浪分钟 K 线）。

    GET /api/v2/read/stock-intraday?code=600519。返回 {code, date, rows:[...], note}；
    rows 列名原样（time/open/high/low/close/volume/amount），缺失->[]；date = 分时
    trade_date（权威），缺失->null。底层源存在，故不走 not_found；仅当整取数失败/空时
    诚实返回 rows=[]、date=null（status 仍 ok，绝不 500 / 编造）。

    prev_close（昨收基准价）：取底层 fetcher 返回的元组第 2 位，用于前端画昨收基准虚线；
    取不到 -> null（前端据此不画基准线并如实标注），绝不补 0 / 不用当日首笔开盘冒充。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"\d{6}", code or ""):
        return fail(message="code 非法（须为 6 位数字股票代码）",
                    code="invalid_param", http_status=400)
    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([("intraday", lambda: _w4c_intraday(code))])
    except Exception:  # noqa: BLE001
        res = {}
    got = res.get("intraday")
    df, prev_close, trade_date = got if isinstance(got, tuple) and len(got) == 3 else (None, None, None)
    rows = []
    date = trade_date or None
    if df is not None and hasattr(df, "columns") and len(df):
        try:
            rows = df.to_dict(orient="records")  # 列名原样透出，不重命名、不补值
        except Exception:  # noqa: BLE001
            rows = []
    data = {
        "code": code,
        "date": date,
        "rows": rows,
        "prev_close": _w4b_num(prev_close),
        "note": _W4C_NOTE + "；分时底层复用 get_stock_intraday_sina（新浪分钟K线），缺失->rows=[]、date=null，绝不编造；prev_close 取底层昨收（取不到->null，绝不补 0）",
    }
    return ok(data=_sanitize(data), message="stock-intraday")


# ───────────── 指数行情只读端点（index-quotes / index-kline）─────────────
# 与 W4-B/W4-C 同款红线：@jwt_required + 统一 ok/fail 信封；code 用 ^(sh|sz)\d{6}$ 校验；
# 多源 fetch_many；异常/空降级为 null/[]，绝不 500、绝不补 0；date 为权威数据日，绝不 now()。
# 数据源 ak.stock_zh_index_daily：离线环境由项目 OFFLINE_MODE 机制返回确定性静态样例，
# 在线返回真实日线；二者均为诚实数据，无编造（与 stock-kline 同源）。
_INDEX_DEFS = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000016", "上证50"),
    ("sh000300", "沪深300"),
]


def _w4x_index_daily(symbol):
    """ak.stock_zh_index_daily(symbol) -> DataFrame | None（异常/空降级）。
    列名中文：日期/开盘/收盘/最高/最低/成交量。"""
    try:
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol=symbol)
    except Exception:  # noqa: BLE001 - 取数失败仅让该指数缺失，不 500
        return None
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        return None
    return df


def _w4x_index_quote(symbol, name):
    """单指数最新报价：当前收盘、昨收、涨跌额、涨跌幅、数据日。取不到 -> 全 None。"""
    df = _w4x_index_daily(symbol)
    if df is None or "收盘" not in df.columns or len(df) == 0:
        return {"code": symbol, "name": name, "current": None, "prev_close": None,
                "change": None, "change_pct": None, "date": None}
    try:
        d = df.sort_values("日期") if "日期" in df.columns else df
        last = d.iloc[-1]
        prev = d.iloc[-2] if len(d) >= 2 else None
        cur = _w4b_num(last.get("收盘"))
        pc = _w4b_num(prev.get("收盘")) if prev is not None else None
        chg = None if (cur is None or pc is None) else round(cur - pc, 4)
        pct = None if (chg is None or not pc) else round(chg / pc * 100, 2)
        date = _w4b_kline_date(d)
        return {"code": symbol, "name": name, "current": cur, "prev_close": pc,
                "change": chg, "change_pct": pct, "date": date}
    except Exception:  # noqa: BLE001
        return {"code": symbol, "name": name, "current": None, "prev_close": None,
                "change": None, "change_pct": None, "date": None}


@bp.get("/index-quotes")
@jwt_required
def index_quotes():
    """主要指数实时报价（外部卡片视角）：上证/深证/创业板/上证50/沪深300。
    GET /api/v2/read/index-quotes。逐指数独立取数、独立降级；全失败返回 items=[] + note。
    """
    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([
            (code, lambda c=code, n=name: _w4x_index_quote(c, n)) for code, name in _INDEX_DEFS
        ])
    except Exception:  # noqa: BLE001
        res = {}
    items = []
    for code, name in _INDEX_DEFS:
        q = res.get(code)
        if not isinstance(q, dict):
            q = {"code": code, "name": name, "current": None, "prev_close": None,
                 "change": None, "change_pct": None, "date": None}
        items.append(q)
    data = {"items": items, "note": _W4C_NOTE}
    return ok(data=_sanitize(data), message="index-quotes")


@bp.get("/index-kline")
@jwt_required
def index_kline():
    """指数日线 K 线（点击卡片打开详情弹窗的数据源）。
    GET /api/v2/read/index-kline?code=sh000001&limit=120。
    rows 英文列 date/open/high/low/close/volume（与 stock-kline 同源，前端 KLineChart 共用）；
    date = 最后一根权威数据日，空则 null。
    """
    code = request.args.get("code", "")
    if not re.fullmatch(r"(sh|sz)\d{6}", code or ""):
        return fail(message="code 非法（须为 sh/sz + 6 位数字指数代码）",
                    code="invalid_param", http_status=400)
    limit = _w4b_limit(120)
    df = _w4x_index_daily(code)
    rows, date = _w4x_index_kline_rows(df, limit)
    data = {"code": code, "rows": rows, "date": date, "note": _W4C_NOTE}
    return ok(data=_sanitize(data), message="index-kline")


def _w4x_index_kline_rows(df, limit):
    """指数日线 -> 英文列 rows；中文列（日期/开盘/收盘/最高/最低/成交量）映射为
    date/open/close/high/low/volume（与 _w4b_kline_rows 同款红线：date 升序、tail(limit)、date 权威）。"""
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        return [], None
    if "日期" not in df.columns or "收盘" not in df.columns:
        return [], None
    rename = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
    try:
        d = df.rename(columns=rename).copy()
        d = d.sort_values("date")
        last = str(d["date"].iloc[-1])[:10] or None
        d = d.tail(limit).copy()
        for col in ("open", "high", "low", "close", "volume"):
            if col not in d.columns:
                d[col] = None
        d["date"] = d["date"].apply(lambda x: str(x)[:10])
        return d[["date", "open", "high", "low", "close", "volume"]].to_dict(orient="records"), last
    except Exception:  # noqa: BLE001
        return [], None


# ───────────── 因子分析（G3：IC/IR、分层收益、多空组合）─────────────
# 契约（与 W4-B/C 同款红线）：@jwt_required + 统一 ok/fail 信封；codes 用 ^\d{6}$ 校验、
# 逗号分隔（≤50）；days/n_layers/forward 经钳制；多标的取数走 fetch_many（整批超时，不阻塞）；
# 任一标的取数失败仅计入 errs，不整页 500、不编造；有效标的 < 3 时**诚实**返回
# status=error（insufficient_data），绝不补零 / 用 < 3 只硬算结论。
# 复用 modules.factor_analysis 纯函数（rank_ic/ic_series/ic_summary/layered_returns/
# cumulative/long_short/build_panels）——逻辑零改动，仅做编排与序列化。
_FA_NOTE = (
    "逐标的独立取数、独立降级；缺失为 null 且不补 0；有效标的<3 不给出因子结论"
    "（与 modules.factor_analysis.build_panels 诚实红线一致）。"
)
_FA_FACTORS = ("momentum", "reversal", "volatility", "turnover")


def _fa_int(raw, default, lo, hi):
    """整参钳制：非法 / 越界回落默认，绝不抛 400（与 _w4b_limit 不同，这里要宽容降级）。"""
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _fa_fetch_hist_factory(res):
    """把 fetch_many 的产出包成 build_panels 期望的 fetch_hist(code) callable。"""
    def _fetch(code):
        df = res.get(code)
        return df if hasattr(df, "columns") and len(df) else None
    return _fetch


@bp.get("/factor-analysis")
@jwt_required
def factor_analysis():
    """因子分析（IC/IR、分层收益、多空组合）。

    GET /api/v2/read/factor-analysis?codes=600519,000001,300750&days=250&factor=momentum&n_layers=5&forward=1
    复用 modules.factor_analysis 纯函数 + page_utils.hist_cached 实时取数；返回三层图表数据
    （IC 序列 / 分层累计 / 多空累计）+ IC 汇总 + 取数错误清单。

    有效标的 < 3 或全取数失败 → 诚实 status=error（insufficient_data），前端据实渲染「数据不足」，
    不补零 / 不编造。date = IC 序列末根权威日期（取不到 null，绝不 now()）。
    """
    raw_codes = (request.args.get("codes") or "").strip()
    codes = [c.strip() for c in raw_codes.split(",") if re.fullmatch(r"\d{6}", c.strip())] if raw_codes else []
    # 用户未指定时给一组演示标的（首页可见、便于联调）；真后端仍逐只实时取数。
    if not codes:
        codes = ["600519", "000001", "300750"]
    if len(codes) > 50:
        return fail(message="codes 过多（≤50）", code="invalid_param", http_status=400)

    days = _fa_int(request.args.get("days"), 250, 20, 1000)
    factor = (request.args.get("factor") or "momentum").strip()
    if factor not in _FA_FACTORS:
        factor = "momentum"
    n_layers = _fa_int(request.args.get("n_layers"), 5, 2, 10)
    forward = _fa_int(request.args.get("forward"), 1, 1, 20)

    # 逐只日线：fetch_many 共享有界池 + 整批超时（避免单标的 akshare 阻塞拖垮整体）。
    try:
        from modules.fetch_parallel import fetch_many
        from modules import page_utils
        res = fetch_many(
            [(c, (lambda c=c: page_utils.hist_cached(c))) for c in codes],
            timeout=CALL_TIMEOUT_CAP,
        )
    except Exception:  # noqa: BLE001 - 并发行异常：全体降级（诚实返回 null）
        res = {}
    fetch_hist = _fa_fetch_hist_factory(res)

    try:
        from modules.factor_analysis import build_panels, ic_series, ic_summary, layered_returns, cumulative, long_short
        fp, ret, errs = build_panels(codes, days, factor, fetch_hist)
    except Exception as e:  # noqa: BLE001 - 纯函数异常：诚实降级，不 500
        return fail(message=f"因子分析计算失败：{type(e).__name__}: {e}", code="compute_error", http_status=200)

    # 诚实红线：有效标的 < 3 → 不给出结论（与 V1 71 页一致）。
    if fp is None or ret is None:
        return fail(
            message="有效标的不足 3 只或取数全部失败，无法得出因子结论",
            code="insufficient_data", http_status=200,
        )

    ic = ic_series(fp, ret, forward)
    summary = ic_summary(ic)
    layered = layered_returns(fp, ret, n_layers, forward)
    layered_cum = cumulative(layered)
    ls = long_short(layered)
    ls_cum = ((1 + ls.fillna(0)).cumprod() - 1) if len(ls) else ls

    def _series_to_rows(s):
        out = []
        for d, v in s.items():
            out.append({"date": str(d)[:10], "ic": (None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v))})
        return out

    ic_rows = _series_to_rows(ic)
    # 分层累计：columns 为层号(0..n-1)，转字符串键 + NaN/Inf → None。
    layered_rows = []
    for d, row in layered_cum.iterrows():
        rec = {"date": str(d)[:10]}
        for col in layered_cum.columns:
            v = row[col]
            rec[str(col)] = None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v)
        layered_rows.append(rec)
    ls_rows = _series_to_rows(ls_cum) if len(ls_cum) else []

    data = {
        "codes": codes,
        "days": days,
        "factor": factor,
        "forward": forward,
        "n_layers": n_layers,
        "ic_series": ic_rows,
        "ic_summary": summary,
        "layered_cum": layered_rows,
        "long_short_cum": ls_rows,
        "errs": [[c, r] for c, r in errs],
        "date": ic_rows[-1]["date"] if ic_rows else None,
        "note": _FA_NOTE,
    }
    return ok(data=_sanitize(data), message="factor-analysis")


# ───────── 策略回测（G3：单标的多因子 / 均线 / 事件驱动回测）─────────
# 契约（与 W4-B/C 同款红线）：@jwt_required + 统一 ok/fail 信封；ticker 用 ^\d{6}$ 校验；
# strategy 限定 event_driven / ma_cross / multi_factor（非法回落 multi_factor）；
# start/end 用 ^\d{4}-\d{2}-\d{2}$ 校验（缺失回落演示窗口）；整段 Backtester.run 套
# run_with_timeout(CALL_TIMEOUT_CAP) 硬边界，绝不因实时取数阻塞拖垮整体；
# 取数为空（df.empty）→ 诚实 status=error（insufficient_data），不补零、不编造；
# NaN/Inf 经 _sanitize 转 null，前端据实渲染「—」/「数据不足」。
_BT_NOTE = (
    "单标的独立回测；取数为空时诚实返回 insufficient_data 而非补零曲线；"
    "total_return/sharpe/win_rate 等口径与 modules.backtest.BacktestResult 一致。"
)
_BT_STRATEGIES = ("event_driven", "ma_cross", "multi_factor")


@bp.get("/backtest")
@jwt_required
def backtest():
    """策略回测。

    GET /api/v2/read/backtest?ticker=600519&start=2024-01-01&end=2024-12-31&strategy=multi_factor
    复用 modules.backtest.Backtester.run（fetch + 信号 + 模拟一体），返回：
    - 摘要指标（total_return_pct / annualized_return_pct / max_drawdown_pct / sharpe_ratio /
      win_rate_pct / profit_factor / avg_trade_return_pct / trade_count / exposure_pct）
    - equity_curve：逐日 {date, cumulative_return, total_asset, drawdown}
    - trades：逐笔 {entry_date, exit_date, entry_price, exit_price, profit_pct, exit_reason, bars_held}
    - date：回测末根权威数据日（取不到 null，绝不 now()）。

    ticker 非法 → fail(400, invalid_param)；start/end 非法 → 回落演示窗口；
    取数为空 → 诚实 status=error（insufficient_data）。
    """
    ticker = (request.args.get("ticker") or "").strip()
    if not re.fullmatch(r"\d{6}", ticker):
        return fail(message="ticker 非法（须为 6 位数字代码）", code="invalid_param", http_status=400)

    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
        start = "2024-01-01"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        end = "2024-12-31"

    strategy = (request.args.get("strategy") or "multi_factor").strip()
    if strategy not in _BT_STRATEGIES:
        strategy = "multi_factor"

    # 整段 run 套硬边界：实时取数阻塞也不会拖垮整体（与 factor-analysis 同款红线）。
    try:
        from modules.timeout_exec import run_with_timeout
        from modules.backtest import Backtester
        bt = Backtester()
        res = run_with_timeout(
            lambda: bt.run(ticker, start, end, strategy=strategy),
            timeout=CALL_TIMEOUT_CAP,
        )
    except Exception as e:  # noqa: BLE001 - 构造/取数异常：诚实降级，不 500
        return fail(message=f"回测执行失败：{type(e).__name__}: {e}", code="compute_error", http_status=200)

    if res is None or res.df is None or res.df.empty:
        return fail(
            message=f"标的 {ticker} 在 {start}~{end} 区间取数为空，无法回测",
            code="insufficient_data", http_status=200,
        )

    # 资金曲线：逐日累计收益 / 总资产 / 回撤（NaN/Inf 经 _sanitize 转 null）。
    equity_curve = []
    for _, row in res.df.iterrows():
        equity_curve.append({
            "date": str(row["date"])[:10],
            "cumulative_return": float(row["cumulative_return"]) if pd.notna(row.get("cumulative_return")) else None,
            "total_asset": float(row["total_asset"]) if pd.notna(row.get("total_asset")) else None,
            "drawdown": float(row["drawdown"]) if pd.notna(row.get("drawdown")) else None,
        })

    # 逐笔交易：日期转字符串、数值落库前 round（NaN/Inf 经 _sanitize 兜底）。
    trades = []
    for t in res.trades:
        trades.append({
            "entry_date": str(t["entry_date"])[:10] if t.get("entry_date") is not None else None,
            "exit_date": str(t["exit_date"])[:10] if t.get("exit_date") is not None else None,
            "entry_price": float(t["entry_price"]) if pd.notna(t.get("entry_price")) else None,
            "exit_price": float(t["exit_price"]) if pd.notna(t.get("exit_price")) else None,
            "profit_pct": float(t["profit_pct"]) if pd.notna(t.get("profit_pct")) else None,
            "exit_reason": t.get("exit_reason"),
            "bars_held": int(t["bars_held"]) if pd.notna(t.get("bars_held")) else None,
        })

    summary = res.summary()
    data = {
        "ticker": ticker,
        "strategy": strategy,
        "start": start,
        "end": end,
        "initial_capital": summary.get("initial_capital"),
        "final_value": summary.get("final_value"),
        "total_return_pct": summary.get("total_return_pct"),
        "annualized_return_pct": summary.get("annualized_return_pct"),
        "max_drawdown_pct": summary.get("max_drawdown_pct"),
        "sharpe_ratio": summary.get("sharpe_ratio"),
        "win_rate_pct": summary.get("win_rate_pct"),
        "profit_factor": summary.get("profit_factor"),
        "avg_trade_return_pct": summary.get("avg_trade_return_pct"),
        "trade_count": summary.get("trade_count"),
        "exposure_pct": summary.get("exposure_pct"),
        "start_date": summary.get("start_date"),
        "end_date": summary.get("end_date"),
        "equity_curve": equity_curve,
        "trades": trades,
        "date": summary.get("end_date") or None,
        "note": _BT_NOTE,
    }
    return ok(data=_sanitize(data), message="backtest")


# ───────── 市场全景 / 状态机（G3：regime_report + shepherd 广度）─────────
# 契约（与 W4-B/C 同款红线）：@jwt_required + 统一 ok/fail 信封；k 经钳制（3~15）；
# 复用 modules.market_regime.regime_report（读 data/shepherd_history.json，离线零网）
# + modules.shepherd_history.get_shepherd_indicators（广度最新快照 + 不可用字段清单）。
# 该端点同时服务于 56 页「市场状态机」与 57 页「市场全景」（两页共用同一后端，不重复计算）。
# regime 不可用（广度历史缺失）→ 诚实 status=error（insufficient_data），不编造状态。
_MP_NOTE = (
    "市场状态五档=规则可解释分类（modules.market_regime，阈值由全样本分位定）；"
    "广度真值=本地历史快照（data/shepherd_history.json，离线零网）；历史相似 ≠ 预测。"
)


@bp.get("/market-panorama")
@jwt_required
def market_panorama():
    """市场全景 / 状态机（56 + 57 页共享后端）。

    GET /api/v2/read/market-panorama?k=8
    返回：
    - regime：regime_report 完整字典（latest 状态/置信/metrics、state_distribution、
      transition_matrix、analogs 历史相似日及后市表现）
    - shepherd_latest：广度最新快照行（红盘率/涨停/跌停/连板高度/炸板率…）
    - shepherd_series：广度历史宽表（折线图用，date 升序）
    - shepherd_unavailable：数据源缺失字段清单（诚实带出，不隐藏）
    - date：regime 最新真值日

    k 非法回落 8；regime 不可用 → 诚实 status=error（insufficient_data）。
    """
    k = _fa_int(request.args.get("k"), 8, 3, 15)

    try:
        from modules import market_regime as mr
        from modules.shepherd_history import get_shepherd_indicators
        regime = mr.regime_report(k=k)
        df, meta = get_shepherd_indicators(days=60)
    except Exception as e:  # noqa: BLE001 - 计算异常：诚实降级，不 500
        return fail(message=f"市场全景计算失败：{type(e).__name__}: {e}", code="compute_error", http_status=200)

    if not regime.get("available"):
        return fail(
            message=regime.get("reason", "广度历史缺失，无法判定市场状态"),
            code="insufficient_data", http_status=200,
        )

    def _row_to_record(row):
        rec = {}
        for c in df.columns:
            v = row[c]
            if pd.isna(v) if not isinstance(v, str) else False:
                rec[str(c)] = None
            elif isinstance(v, (int, float)):
                rec[str(c)] = float(v)
            else:
                rec[str(c)] = str(v)
        return rec

    shepherd_latest = {}
    shepherd_series = []
    if df is not None and not df.empty:
        shepherd_latest = _row_to_record(df.iloc[-1])
        shepherd_series = [_row_to_record(r) for _, r in df.iterrows()]

    unavailable = []
    if isinstance(meta, dict):
        unavailable = [[str(x[0]), str(x[1])] for x in meta.get("unavailable", []) if isinstance(x, (list, tuple))]

    data = {
        "k": k,
        "regime": regime,
        "shepherd_latest": shepherd_latest,
        "shepherd_series": shepherd_series,
        "shepherd_unavailable": unavailable,
        "date": (regime.get("latest") or {}).get("date"),
        "note": _MP_NOTE,
    }
    return ok(data=_sanitize(data), message="market-panorama")


# ───────── 持仓中心（G3：本地模拟持仓 + FIFO 盈亏 + 收益归因）─────────
# 契约（同款红线）：@jwt_required + 统一 ok/fail 信封；只读 data/portfolio.csv（本地模拟持仓）；
# 现价经 StockFetcher.get_daily 取最近收盘（离线静态样本，属「模拟/历史数据」口径）；
# 取数异常回落买入价并诚实标注 price_source='fallback'；净值是尽力而为的历史曲线，
# 取不到日线则 curve_available=False 而非补零；持仓文件缺失/为空 → insufficient_data。
_PF_NOTE = (
    "持仓为本地模拟/历史数据（data/portfolio.csv），仅供学习不构成投资建议；"
    "现价为最近可得收盘（离线口径可能为静态样本）；净值曲线为尽力而为的历史还原，缺失则如实标注。"
)
_PF_BENCH = "000300"  # 沪深300，收益归因素基准


def _flt(v):
    """转原生 float；None / 非数 / NaN / Inf → None（避免 numpy 类型与 JSON 序列化失败）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _int(v):
    """转原生 int；None / 非数 → None。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _build_portfolio_curve(pm, pnl, attr):
    """尽力而为的组合净值曲线（基准沪深300）。

    对每只仍有剩余持仓的标的取日线，按剩余股数加权还原组合市值序列，归一化到起点 100；
    基准同样归一化到 100。任一日线缺失 / 取不到公共日期 → 诚实返回 ([], False)。
    绝不以买入价线性外推编造曲线（诚实红线）。
    """
    try:
        remaining = {}
        for _, r in pnl.iterrows():
            t = str(r["ticker"])
            rs = _int(r.get("remaining_shares")) or 0
            if rs > 0:
                remaining[t] = rs
        if not remaining:
            return [], False, "no_open_positions"

        # 取数窗口：最早买入日往前 120 天 ~ 今
        earliest = None
        for _, r in pnl.iterrows():
            bd = str(r.get("buy_date") or "")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", bd):
                earliest = bd if earliest is None else min(earliest, bd)
        start = (datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d") if earliest else "2024-01-01"

        series = {}
        for t, rs in remaining.items():
            df = pm.fetcher.get_daily(t, start=start, end=None)
            if df is None or df.empty or "close" not in df.columns:
                return [], False, f"daily_missing:{t}"
            df = df.copy()
            df["_d"] = df.index if df.index.name else df.get("date")
            # 归一化到起点 100
            closes = df["close"].astype(float).tolist()
            if not closes or closes[0] == 0:
                return [], False, f"bad_close:{t}"
            base = closes[0]
            series[t] = {
                "dates": [str(x)[:10] for x in (df.index if not df.index.name else df.index)],
                "norm": [c / base * 100 for c in closes],
                "shares": rs,
            }

        # 对齐公共日期
        common = None
        for s in series.values():
            dset = set(s["dates"])
            common = dset if common is None else (common & dset)
        if not common or len(common) < 2:
            return [], False, "no_common_dates"

        common = sorted(common)
        idx = {d: i for i, d in enumerate(common)}
        # 组合加权净值
        combo = [0.0] * len(common)
        for s in series.values():
            pos = {d: v for d, v in zip(s["dates"], s["norm"])}
            for d in common:
                combo[idx[d]] += pos[d] * s["shares"]
        total_shares = sum(s["shares"] for s in series.values())
        combo = [c / total_shares * 100 for c in combo]

        # 基准
        bench = [None] * len(common)
        try:
            bdf = pm.fetcher.get_daily(_PF_BENCH, start=start, end=None)
            if bdf is not None and not bdf.empty and "close" in bdf.columns:
                bcloses = bdf["close"].astype(float).tolist()
                bdates = [str(x)[:10] for x in bdf.index]
                bbase = bcloses[0] if bcloses and bcloses[0] != 0 else None
                if bbase:
                    bmap = {d: c / bbase * 100 for d, c in zip(bdates, bcloses)}
                    bench = [bmap.get(d) for d in common]
        except Exception:  # noqa: BLE001 - 基准缺失只影响基准线，不影响组合线
            bench = [None] * len(common)

        curve = [
            {"date": common[i], "portfolio": _flt(combo[i]), "benchmark": _flt(bench[i])}
            for i in range(len(common))
        ]
        return curve, True, None
    except Exception as e:  # noqa: BLE001 - 任何异常：诚实降级
        return [], False, f"{type(e).__name__}: {e}"


@bp.get("/portfolio")
@jwt_required
def portfolio():
    """持仓中心（45 页）。

    GET /api/v2/read/portfolio
    返回：
    - summary：total_cost / total_market_value / total_pnl / total_pnl_pct / position_count
    - positions：逐批持仓（ticker/name/buy_date/buy_price/shares/remaining_shares/cost/
      current_price/market_value/realized_pnl/pnl/pnl_pct）
    - attribution：按个股聚合的盈亏贡献（ticker/name/pnl/pnl_pct/contribution）
    - weights：市值占比（ticker/name/weight_pct）
    - curve：尽力而为的组合净值曲线（date/portfolio/benchmark，基准沪深300）
    - curve_available：bool（日线取不到则 False）
    - note / unavailable：诚实口径与缺失清单

    持仓文件缺失/为空 → 诚实 status=error（insufficient_data）。
    """
    try:
        from modules.portfolio import PortfolioManager
        pm = PortfolioManager()
        pnl = pm.calc_pnl()
        if pnl is None or (hasattr(pnl, "empty") and pnl.empty):
            return fail(message="本地持仓文件为空或缺失", code="insufficient_data", http_status=200)
        summary = pm.summary()
        attr = pm.pnl_attribution()
    except Exception as e:  # noqa: BLE001 - 计算异常：诚实降级，不 500
        return fail(message=f"持仓计算失败：{type(e).__name__}: {e}", code="compute_error", http_status=200)

    positions = []
    for _, r in pnl.iterrows():
        positions.append({
            "ticker": str(r["ticker"]),
            "name": str(r.get("name") or ""),
            "buy_date": str(r.get("buy_date") or ""),
            "buy_price": _flt(r.get("buy_price")),
            "shares": _int(r.get("shares")),
            "remaining_shares": _int(r.get("remaining_shares")),
            "cost": _flt(r.get("cost")),
            "current_price": _flt(r.get("current_price")),
            "market_value": _flt(r.get("market_value")),
            "realized_pnl": _flt(r.get("realized_pnl")),
            "pnl": _flt(r.get("pnl")),
            "pnl_pct": _flt(r.get("pnl_pct")),
        })

    attribution = []
    for _, r in attr.iterrows():
        attribution.append({
            "ticker": str(r["ticker"]),
            "name": str(r.get("name") or ""),
            "pnl": _flt(r.get("pnl")),
            "pnl_pct": _flt(r.get("pnl_pct")),
            "contribution": _flt(r.get("contribution")),
        })

    total_mv = float(sum((p["market_value"] or 0) for p in positions))
    weights = []
    if total_mv > 0:
        for p in positions:
            weights.append({
                "ticker": p["ticker"], "name": p["name"],
                "weight_pct": round((p["market_value"] or 0) / total_mv * 100, 2),
            })

    curve, curve_available, _ = _build_portfolio_curve(pm, pnl, attr)

    data = {
        "summary": {k: _flt(v) for k, v in (summary or {}).items()},
        "positions": positions,
        "attribution": attribution,
        "weights": weights,
        "curve": curve,
        "curve_available": curve_available,
        "date": None,
        "note": _PF_NOTE,
        "unavailable": [],
    }
    return ok(data=_sanitize(data), message="portfolio")


# ───────── 资金流向（35 页）─────────
# 分块诚实降级：北向 / 行业 / 大盘主力 / 融资融券 四块各自独立 available；
# 任一网络取数失败只影响该块（available=False + 空数据），不整页 500、不补 0；
# 金额统一折算为「亿元」（元 /1e8），缺失/未披露为 null；百分比保留原始百分数。
_FF_NOTE = (
    "资金流向数据来自东方财富/同花顺网络接口（fundflow / margin_trading 数据层），离线或接口受限时"
    "逐块诚实降级（该块显示「数据暂不可用」而非编造数值）。北向实时净买额自 2024-08-16 起停披露，"
    "模块以「最近一次真实披露」与「历史累计净买入」兜底；金额单位均为亿元，非实时、非投资建议。"
)


def _ff_yi(v):
    """元 -> 亿元；None/NaN/inf/非法 -> None（缺失即 null，绝不补 0）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f / 1e8


def _ff_date(v):
    try:
        if v is None:
            return None
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        s = str(v)
        return s[:10] if s else None
    except Exception:  # noqa: BLE001
        return None


@bp.get("/fund-flow")
@jwt_required
def fund_flow():
    """资金流向（35 页）。分块诚实降级。

    GET /api/v2/read/fund-flow
    返回四块：northbound / industry / market / margin，每块独立 available 标志；
    网络取数失败 -> 该块 available=False + 空数据；全局 note / unavailable 诚实标注。
    """
    unavailable = []
    try:
        from modules.fundflow import (
            get_northbound_fund_flow, get_industry_fund_flow, get_market_fund_flow,
        )
        from modules.margin_trading import get_margin_trading_data, get_latest_margin_summary
        from modules.fetch_parallel import fetch_many

        tasks = [
            ("northbound", get_northbound_fund_flow),
            ("industry", get_industry_fund_flow),
            ("market", lambda: get_market_fund_flow(days=30)),
            ("margin", lambda: get_margin_trading_data(days=180)),
            ("margin_summary", get_latest_margin_summary),
        ]
        res = fetch_many(tasks, max_workers=5, timeout=14)
    except Exception:  # noqa: BLE001 - 取数框架级异常：整页诚实降级
        res = {}
        unavailable.append("fetch_many")

    # ── 北向资金 ──
    nb_block = {
        "available": False, "trade_date": None, "total_inflow": None, "sh_inflow": None,
        "sz_inflow": None, "northbound_net_available": False, "boards": [],
        "last_net_buy": None, "last_net_buy_date": None, "cumulative": None,
        "cumulative_date": None,
    }
    nb = res.get("northbound")
    if nb is None:
        unavailable.append("northbound")
    else:
        try:
            nb_block["trade_date"] = nb.get("trade_date")
            nb_block["total_inflow"] = _ff_yi(nb.get("total_inflow"))
            nb_block["sh_inflow"] = _ff_yi(nb.get("sh_inflow"))
            nb_block["sz_inflow"] = _ff_yi(nb.get("sz_inflow"))
            nb_block["northbound_net_available"] = bool(nb.get("northbound_net_available"))
            nb_block["last_net_buy"] = _ff_yi(nb.get("last_net_buy"))
            nb_block["last_net_buy_date"] = nb.get("last_net_buy_date")
            nb_block["cumulative"] = _ff_yi(nb.get("cumulative"))
            nb_block["cumulative_date"] = nb.get("cumulative_date")
            boards = []
            for b in (nb.get("boards") or []):
                boards.append({
                    "board": b.get("板块"),
                    "direction": b.get("资金方向"),
                    "trade_net": _ff_yi(b.get("成交净买额")),
                    "net_inflow": _ff_yi(b.get("资金净流入")),
                    "up_count": _int(b.get("上涨数")),
                    "down_count": _int(b.get("下跌数")),
                    "index_chg_pct": _flt(b.get("指数涨跌幅")),
                })
            nb_block["boards"] = boards
            nb_block["available"] = bool(
                nb.get("trade_date") or boards
                or nb.get("last_net_buy") is not None or nb.get("cumulative") is not None
            )
        except Exception:  # noqa: BLE001
            nb_block["available"] = False
            unavailable.append("northbound")

    # ── 行业板块资金流向 ──
    ind_block = {"available": False, "rows": []}
    ind = res.get("industry")
    if ind is None:
        unavailable.append("industry")
    else:
        try:
            rows = []
            if ind is not None and not getattr(ind, "empty", True):
                for _, r in ind.iterrows():
                    rows.append({
                        "industry": r.get("行业"),
                        "chg_pct": _flt(r.get("涨跌幅")),
                        "inflow": _ff_yi(r.get("流入资金")),
                        "outflow": _ff_yi(r.get("流出资金")),
                        "net": _ff_yi(r.get("净额")),
                        "leader": r.get("领涨股"),
                        "leader_chg_pct": _flt(r.get("领涨股涨跌幅")),
                    })
            ind_block["rows"] = rows
            ind_block["available"] = bool(rows)
        except Exception:  # noqa: BLE001
            ind_block["available"] = False
            unavailable.append("industry")

    # ── 大盘主力资金净流入（近 30 日）──
    mkt_block = {"available": False, "rows": []}
    mk = res.get("market")
    if mk is None:
        unavailable.append("market")
    else:
        try:
            rows = []
            if mk is not None and not getattr(mk, "empty", True):
                for _, r in mk.iterrows():
                    rows.append({
                        "date": _ff_date(r.get("日期")),
                        "index_chg_pct": _flt(r.get("上证-涨跌幅")),
                        "main_net": _ff_yi(r.get("主力净流入-净额")),
                        "main_net_pct": _flt(r.get("主力净流入-净占比")),
                        "super_net": _ff_yi(r.get("超大单净流入-净额")),
                        "big_net": _ff_yi(r.get("大单净流入-净额")),
                        "mid_net": _ff_yi(r.get("中单净流入-净额")),
                    })
            mkt_block["rows"] = rows
            mkt_block["available"] = bool(rows)
        except Exception:  # noqa: BLE001
            mkt_block["available"] = False
            unavailable.append("market")

    # ── 融资融券 ──
    mg_block = {"available": False, "rows": [], "latest": None}
    mg = res.get("margin")
    if mg is None:
        unavailable.append("margin")
    else:
        try:
            rows = []
            if mg is not None and not getattr(mg, "empty", True):
                for _, r in mg.iterrows():
                    rows.append({
                        "date": _ff_date(r.get("日期")),
                        "sh_rzmr_yi": _ff_yi(r.get("sh_rzmr")),
                        "sz_rzmr_yi": _ff_yi(r.get("sz_rzmr")),
                        "total_rzmr_yi": _ff_yi(r.get("total_rzmr")),
                        "sh_rzye_yi": _ff_yi(r.get("sh_rzye")),
                        "sz_rzye_yi": _ff_yi(r.get("sz_rzye")),
                        "total_rzye_yi": _ff_yi(r.get("total_rzye")),
                        "sh000001": _flt(r.get("sh000001")),
                        "sz399001": _flt(r.get("sz399001")),
                        "sz399006": _flt(r.get("sz399006")),
                    })
            mg_block["rows"] = rows
            summary = res.get("margin_summary") or {}
            mg_block["latest"] = {
                "date": _ff_date(summary.get("date")),
                "total_rzmr_yi": _flt(summary.get("total_rzmr_yi")),
                "total_rzye_yi": _flt(summary.get("total_rzye_yi")),
                "sh_rzmr_yi": _flt(summary.get("sh_rzmr_yi")),
                "sz_rzmr_yi": _flt(summary.get("sz_rzmr_yi")),
                "rzmr_change_yi": _flt(summary.get("rzmr_change_yi")),
                "rzye_change_yi": _flt(summary.get("rzye_change_yi")),
                "rzmr_change_pct": _flt(summary.get("rzmr_change_pct")),
                "rzye_change_pct": _flt(summary.get("rzye_change_pct")),
            } if summary else None
            mg_block["available"] = bool(rows) or bool(summary)
        except Exception:  # noqa: BLE001
            mg_block["available"] = False
            unavailable.append("margin")

    data = {
        "northbound": nb_block,
        "industry": ind_block,
        "market": mkt_block,
        "margin": mg_block,
        "note": _FF_NOTE,
        "unavailable": unavailable,
    }
    return ok(data=_sanitize(data), message="fund-flow")


# ───────── 板块轮动（只读 / sector-rotation）─────────
@bp.get("/sector-rotation")
@jwt_required
def sector_rotation():
    """板块轮动热力图（12 页 V2 化）。复用 modules.fundflow.get_industry_fund_flow。

    返回行业级 涨跌幅 + 资金净额 + 领涨股，供前端热力图/排行榜/强弱象限渲染。
    取数空或解析异常 -> 诚实降级（items=[] + unavailable 标注），不 500、不补 0。
    （v1 的「行业资金流→板块涨跌列表」二级降级在 V2 收敛为单源行业资金流，
     网络失败时如实标注「行业资金流不可用」而非伪造板块列表。）
    """
    unavailable = []
    src_label = None
    items = []
    try:
        from modules.fundflow import get_industry_fund_flow
        df = get_industry_fund_flow()
    except Exception:  # noqa: BLE001 - 取数框架级异常：整页诚实降级
        df = None
    if df is None or getattr(df, "empty", True):
        unavailable.append("industry_flow_unavailable")
        src_label = "行业资金流不可用"
    else:
        try:
            src_label = "行业资金流(akshare)"
            for _, r in df.iterrows():
                items.append({
                    "name": r.get("行业"),
                    "chg_pct": _flt(r.get("涨跌幅")),
                    "net": _ff_yi(r.get("净额")),
                    "leader": r.get("领涨股"),
                    "leader_chg_pct": _flt(r.get("领涨股涨跌幅")),
                })
        except Exception:  # noqa: BLE001 - 解析异常：降级为空，不 500
            items = []
            unavailable.append("industry_flow_parse_failed")
            src_label = "行业资金流解析失败"
    data = {
        "items": items,
        "src_label": src_label,
        "unavailable": unavailable,
        "date": None,
    }
    return ok(data=_sanitize(data), message="sector-rotation")


# ───────── 智能盯盘（只读 / watch）─────────
# 诚实口径：V2 此处**只读**聚合，复用用户自选股（本地 Watchlist/Stock，JWT 隔离）+ 板块资金异动
# （get_industry_fund_flow）+ 逐只自选股主力资金流（get_individual_fund_flow，Flask 安全、并行有界）。
# ⚠️ 不在只读端点 fan-out 实时行情：quote_one 依赖 Streamlit 单例（@st.cache_resource + import streamlit），
#   Flask 上下文不可用，故「实时现价/涨跌幅、价变阈值预警」未聚合；页面如实标注，看实时价请用
#   个股分时/行情端点或 v1 实时盯盘页。资金流预警基于主力净流入占比阈值，非价格。
_WATCH_NOTE = (
    "本页为 V2 只读盯盘聚合：自选股（本地自选列表，按当前账号隔离）+ 板块资金异动（行业资金流）"
    "+ 逐只自选股主力资金流（真实优先、量价估算兜底）。实时现价/涨跌幅未在此只读端点聚合"
    "（实时行情取数依赖 Streamlit 单例，Flask 上下文不可用），需看实时价请用个股分时/行情端点或 v1 盯盘页；"
    "资金流预警基于主力净流入占比阈值，非价格。数据为加载时点快照，非实时，非投资建议。"
)


@bp.get("/watch")
@jwt_required
def watch():
    """智能盯盘聚合（14 页 V2 化）。

    返回：watchlist（自选股 + 每只主力资金流）、sector_items（行业资金流异动）、
    alerts（资金流阈值预警）、summary、src_labels、unavailable、note。
    任一取数失败 → 诚实降级（对应块为空 + unavailable 标注），不 500、不补 0。
    """
    unavailable: list[str] = []
    watchlist: list[dict] = []
    sector_items: list[dict] = []
    alerts: list[dict] = []

    # ── 1) 自选股（复用 config_routes 同款查询：Watchlist + Stock 名称反查）──
    wl: list[dict] = []
    try:
        from flask import g
        from ..extensions import db
        from ..models import Watchlist, Stock
        from sqlalchemy import select as _select

        rows = db.session.execute(
            _select(Watchlist)
            .where(Watchlist.user_id == g.current_user.id)
            .order_by(Watchlist.created_at.desc())
        ).scalars()
        for w in rows:
            stock = db.session.execute(
                _select(Stock).where(Stock.code == w.stock_code)
            ).scalar_one_or_none()
            wl.append({
                "code": w.stock_code,
                "name": stock.name if stock else w.stock_code,
                "note": w.note,
            })
    except Exception:  # noqa: BLE001 - DB 查询异常：降级为空，不 500
        wl = []
        unavailable.append("watchlist_query_failed")

    # ── 2) 逐只主力资金流（Flask 安全；并行有界，整体超时 20s）──
    fund_by_code: dict[str, object] = {}
    if wl:
        try:
            from modules.fundflow import get_individual_fund_flow
            from modules.fetch_parallel import fetch_many

            def _mk(code: str):
                return lambda: get_individual_fund_flow(code, use_estimate_fallback=True, timeout=12.0)

            tasks = [(w["code"], _mk(w["code"])) for w in wl]
            fund_by_code = fetch_many(tasks, max_workers=5, timeout=20) or {}
        except Exception:  # noqa: BLE001 - 取数框架级异常：整体降级，不 500
            unavailable.append("watchlist_fund_failed")

    for w in wl:
        code = w["code"]
        ff = fund_by_code.get(code)
        if isinstance(ff, dict):
            fund = {
                "source": ff.get("source"),
                "main_net": _ff_yi(ff.get("main_net")),          # 元 -> 亿元
                "main_net_pct": _flt(ff.get("main_net_pct")),     # 已是百分比，原样
                "big_net": _ff_yi(ff.get("big_net")),
                "super_net": _ff_yi(ff.get("super_net")),
                "latest_date": ff.get("latest_date"),
            }
        else:
            fund = {
                "source": None, "main_net": None, "main_net_pct": None,
                "big_net": None, "super_net": None, "latest_date": None,
            }
        watchlist.append({**w, "fund": fund})

        # 资金流阈值预警（基于主力净流入占比，非价格）
        if isinstance(ff, dict) and ff.get("source") not in (None, "none"):
            pct = fund["main_net_pct"]
            if pct is not None:
                if pct >= 3.0:
                    level, reason = "强", f"主力净流入占比 +{pct:.2f}%（强）"
                elif pct <= -3.0:
                    level, reason = "弱", f"主力净流出占比 {pct:.2f}%（弱）"
                else:
                    level, reason = "中性", f"主力净流入占比 {pct:+.2f}%（中性）"
            else:
                level, reason = "中性", "主力净流入占比数据缺失"
        else:
            level, reason = "未知", "资金流数据缺失（来源不可用）"
        alerts.append({"code": code, "name": w["name"], "level": level, "reason": reason})

    # ── 3) 板块资金异动（复用 get_industry_fund_flow）──
    try:
        from modules.fundflow import get_industry_fund_flow

        idf = get_industry_fund_flow()
    except Exception:  # noqa: BLE001 - 取数框架级异常：降级为空，不 500
        idf = None
    if idf is None or getattr(idf, "empty", True):
        unavailable.append("sector_flow_unavailable")
    else:
        try:
            for _, r in idf.iterrows():
                sector_items.append({
                    "name": r.get("行业"),
                    "chg_pct": _flt(r.get("涨跌幅")),
                    "net": _ff_yi(r.get("净额")),
                    "leader": r.get("领涨股"),
                    "leader_chg_pct": _flt(r.get("领涨股涨跌幅")),
                })
        except Exception:  # noqa: BLE001 - 解析异常：降级为空，不 500
            sector_items = []
            unavailable.append("sector_flow_parse_failed")

    with_fund = sum(
        1 for w in watchlist
        if (w.get("fund") or {}).get("source") and (w["fund"]["source"] != "none")
    )
    strong_cnt = sum(1 for a in alerts if a["level"] == "强")
    weak_cnt = sum(1 for a in alerts if a["level"] == "弱")

    data = {
        "watchlist": watchlist,
        "sector_items": sector_items,
        "alerts": alerts,
        "summary": {
            "watch_count": len(watchlist),
            "with_fund": with_fund,
            "strong_count": strong_cnt,
            "weak_count": weak_cnt,
            "sector_available": len(sector_items) > 0,
        },
        "src_labels": {
            "watchlist_fund": "个股主力资金流(akshare/估算)",
            "sector": "行业资金流(akshare)" if len(sector_items) > 0 else None,
        },
        "unavailable": unavailable,
        "note": _WATCH_NOTE,
    }
    return ok(data=_sanitize(data), message="watch")


# ───────── 实盘交易（只读概览 / trading-account）─────────
# 诚实口径：V2 此处**只读**，聚合本地模拟账本 data/paper_<user>.json（模拟撮合下的
# 账户/持仓/订单流水），**不暴露任何写接口**；实时下单与真实券商（QMT/同花顺）写能力
# 仅在 v1 实盘交易页 /api/trade/* 提供。缺账本 → 诚实返回空（不 500、不补 0）。
_TRADE_NOTE = (
    "本页为 V2 只读概览，读取本地模拟账本（data/paper_<user>.json），反映模拟撮合下的账户 / 持仓 / "
    "订单流水，非真实券商实盘；实时下单与真实券商（QMT / 同花顺）写能力仅在 v1 实盘交易页 /api/trade/* "
    "提供，V2 不暴露任何写接口。数据仅供参考，非投资建议。"
)


@bp.get("/trading-account")
@jwt_required
def trading_account():
    """实盘交易只读概览（43 页 V2 化）。聚合本地模拟账本，四态诚实降级。

    GET /api/v2/read/trading-account?user=<uid>
    返回 account / positions / orders 三块；无账本则 available=False + 空数据。
    """
    user = (request.args.get("user") or "admin").strip()
    if not _USER_RE.fullmatch(user):
        return fail(message="user 非法（仅允许字母/数字/下划线，≤64）", code="validation_error", http_status=400)
    path = _safe_file(_DATA_DIR, f"paper_{user}.json")
    if path is None:
        return fail(message="非法路径", code="validation_error", http_status=400)

    status, raw = _read_json(path)
    if status != "ok" or not isinstance(raw, dict):
        # 无账本：诚实返回空（不 500、不补 0）
        data = {
            "account": {
                "broker_type": "sim", "mode": "模拟", "init_cash": None, "cash": None,
                "position_cost": None, "total_assets": None, "available": False,
            },
            "positions": [], "orders": [], "note": _TRADE_NOTE, "unavailable": ["ledger_missing"],
        }
        return ok(data=_sanitize(data), message="trading-account")

    try:
        init_cash = _flt(raw.get("init_cash"))
        cash = _flt(raw.get("cash"))

        positions: list[dict] = []
        position_cost = 0.0
        positions_raw = raw.get("positions") or {}
        if isinstance(positions_raw, dict):
            for code, p in positions_raw.items():
                if not isinstance(p, dict):
                    continue
                qty = _flt(p.get("qty"))
                avg_cost = _flt(p.get("avg_cost"))
                cost_basis = (qty * avg_cost) if (qty is not None and avg_cost is not None) else None
                if cost_basis is not None:
                    position_cost += cost_basis
                positions.append({
                    "code": code,
                    "name": p.get("name"),
                    "qty": qty,
                    "avg_cost": avg_cost,
                    "cost_basis": cost_basis,
                })

        orders: list[dict] = []
        trades = raw.get("trades") or []
        if isinstance(trades, list):
            for t in trades:
                if not isinstance(t, dict):
                    continue
                orders.append({
                    "time": t.get("time"),
                    "code": t.get("code"),
                    "name": t.get("name"),
                    "side": t.get("side"),  # 买 / 卖
                    "price": _flt(t.get("price")),
                    "qty": _flt(t.get("qty")),
                    "amount": _flt(t.get("amount")),
                })

        total_assets = (cash + position_cost) if (cash is not None and position_cost is not None) else None
        data = {
            "account": {
                "broker_type": "sim", "mode": "模拟",
                "init_cash": init_cash, "cash": cash,
                "position_cost": position_cost or None,
                "total_assets": total_assets,
                "available": True,
            },
            "positions": positions,
            "orders": orders,
            "note": _TRADE_NOTE,
            "unavailable": [],
        }
        return ok(data=_sanitize(data), message="trading-account")
    except Exception:  # noqa: BLE001 - 账本解析异常：诚实降级
        data = {
            "account": {"broker_type": "sim", "mode": "模拟", "init_cash": None, "cash": None,
                        "position_cost": None, "total_assets": None, "available": False},
            "positions": [], "orders": [], "note": _TRADE_NOTE, "unavailable": ["ledger_parse"],
        }
        return ok(data=_sanitize(data), message="trading-account")


@bp.get("/macro-data")
@jwt_required
def macro_data():
    """宏观数据只读聚合（84 页 V2 化）。复用 modules.macro_data.fetch_all +
    global_regime_score；各指标独立降级（取不到→None），绝不补 0。

    GET /api/v2/read/macro-data
    返回 indicators(各指标字典或 None) + regime(全球风险评分或 None) + unavailable。
    """
    try:
        from modules import macro_data as md
        indicators = md.fetch_all()
        regime = md.global_regime_score()
    except Exception:  # noqa: BLE001 - 取数整体异常：诚实返回空，不 500
        indicators = None
        regime = None

    if indicators is None:
        data = {
            "indicators": {},
            "regime": None,
            "unavailable": ["macro_fetch_failed"],
        }
        return ok(data=_sanitize(data), message="macro-data")

    # 逐指标诚实降级：None 即取不到；unavailable 列出缺失 key，页面如实标注、不编造。
    missing = [k for k, v in indicators.items() if v is None]
    data = {
        "indicators": indicators,
        "regime": regime,
        "unavailable": missing,
    }
    return ok(data=_sanitize(data), message="macro-data")


# ───────── 龙虎榜（85 页 V2 化）─────────
def _lhb_yi(v):
    """净买额（元）→ 亿元，非有限值→None。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f / 1e8


def _lhb_str(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    s = str(v)
    if s in ("", "nan", "None", "NaN"):
        return None
    return s


def _lhb_normalize(part):
    """summarize 产出的 buy_top/sell_top DataFrame → [{code,name,net_yi}]；空→None。"""
    if part is None or not hasattr(part, "empty") or part.empty:
        return None
    from modules import lhb as _lhb
    code_col = _lhb.find_col(part, _lhb.CODE_CANDS)
    name_col = _lhb.find_col(part, _lhb.NAME_CANDS)
    rows = []
    for _, r in part.iterrows():
        rows.append({
            "code": _lhb_str(r[code_col]) if code_col else None,
            "name": _lhb_str(r[name_col]) if name_col else None,
            "net_yi": _lhb_yi(r.get("净买额")),
        })
    return rows


def _lhb_records(df, cap=200):
    """原始明细 → list[dict]（to_json 已把 NaN 转 null，且产出原生数值类型）。"""
    if df is None or not hasattr(df, "empty") or df.empty:
        return None
    try:
        import json
        return json.loads(df.head(cap).to_json(orient="records"))
    except Exception:  # noqa: BLE001
        return None


def _to_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _to_int(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return int(round(f))


def _safe_str(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    s = str(v)
    if s in ("", "nan", "None", "NaN"):
        return None
    return s


@bp.get("/dragon-tiger")
@jwt_required
def dragon_tiger():
    """龙虎榜只读聚合（85 页 V2 化）。复用 modules.lhb.fetch_lhb(date) + summarize(df)。

    红线（与 modules.lhb 一致）：
    - 取不到（akshare 缺失 / 网络失败 / 非交易日）→ 仍 200、unavailable=['lhb_fetch_failed']，不 500。
    - summarize 返回 None（净买额列识别不到）→ 不猜列编资金方向，buy_top/sell_top 降级为 None，
      但诚实保留原始明细（detail），让用户自己看。
    - 所有数值后端已把 NaN/Inf 清洗为 null，前端不补 0。

    GET /api/v2/read/dragon-tiger?date=YYYYMMDD  （date 缺省用今天）
    返回 date/count/net_col/net_sum_yi/buy_top/sell_top(各 [code,name,net_yi])/detail/ unavailable。
    """
    date = (request.args.get("date") or "").strip() or None
    try:
        from modules import lhb
        df = lhb.fetch_lhb(date)
    except Exception:  # noqa: BLE001
        df = None

    if df is None:
        data = {
            "date": date,
            "count": None,
            "net_col": None,
            "net_sum_yi": None,
            "buy_top": None,
            "sell_top": None,
            "detail": None,
            "unavailable": ["lhb_fetch_failed"],
        }
        return ok(data=_sanitize(data), message="dragon-tiger")

    summary = lhb.summarize(df)
    if summary is None:
        # 明细取到，但净买列识别不到：不显示排名（宁缺毋滥），诚实给原始明细。
        data = {
            "date": date,
            "count": None,
            "net_col": None,
            "net_sum_yi": None,
            "buy_top": None,
            "sell_top": None,
            "detail": _lhb_records(df, cap=200),
            "unavailable": ["net_col_missing"],
        }
        return ok(data=_sanitize(data), message="dragon-tiger")

    data = {
        "date": date,
        "count": summary["count"],
        "net_col": summary["net_col"],
        "net_sum_yi": _lhb_yi(summary["net_sum"]),
        "buy_top": _lhb_normalize(summary["buy_top"]),
        "sell_top": _lhb_normalize(summary["sell_top"]),
        "detail": _lhb_records(df, cap=200),
        "unavailable": [],
    }
    return ok(data=_sanitize(data), message="dragon-tiger")


# ───────── 题材热点（75 页 V2 化）─────────
@bp.get("/theme")
@jwt_required
def theme():
    """题材/概念热度只读聚合（75 页 V2 化）。复用 modules.theme_heat.load_concepts()。

    返回概念板块快照的派生字段（name/chg/turnover_p/lifecycle/mv/turnover/up/down/leader）+
    汇总（概念数/上涨/下跌/领涨题材）+ 生命周期分布计数。

    红线：取不到快照→仍 200、unavailable=['theme_concepts_unavailable']、concepts=[]，不 500、不编数据；
    生命周期为启发式分类（涨跌幅+换手分位），非预测。
    """
    try:
        from modules import theme_heat as th
        df = th.load_concepts()
    except Exception:  # noqa: BLE001
        df = None

    if df is None or getattr(df, "empty", True):
        data = {
            "concepts": [],
            "summary": None,
            "lifecycle_counts": {},
            "unavailable": ["theme_concepts_unavailable"],
        }
        return ok(data=_sanitize(data), message="theme")

    name_c = th.col_of(df, "name")
    chg = df["_chg"]
    tp = df["_turnover_p"]
    life = df["_life"]
    mv_c = th.col_of(df, "mv")
    turnover_c = th.col_of(df, "turnover")
    up_c = th.col_of(df, "up")
    down_c = th.col_of(df, "down")
    leader_c = th.col_of(df, "leader")

    if name_c is None:
        # 缺板块名称字段：无法绘制热力图/排名，诚实降级
        data = {
            "concepts": [],
            "summary": None,
            "lifecycle_counts": {},
            "unavailable": ["theme_name_field_missing"],
        }
        return ok(data=_sanitize(data), message="theme")

    concepts = []
    for _, r in df.iterrows():
        concepts.append({
            "name": _safe_str(r.get(name_c)),
            "chg": _to_float(r["_chg"]),
            "turnover_p": _to_float(r["_turnover_p"]),
            "lifecycle": _safe_str(r.get("_life")),
            "mv": _to_float(r.get(mv_c)) if mv_c else None,
            "turnover": _to_float(r.get(turnover_c)) if turnover_c else None,
            "up": _to_int(r.get(up_c)) if up_c else None,
            "down": _to_int(r.get(down_c)) if down_c else None,
            "leader": _safe_str(r.get(leader_c)) if leader_c else None,
        })

    n_up = int((chg > 0).sum())
    n_down = int((chg < 0).sum())
    life_counts = {str(k): int(v) for k, v in life.value_counts().items()}

    summary = {
        "count": int(len(df)),
        "n_up": n_up,
        "n_down": n_down,
        "top_name": None,
        "top_chg": None,
    }
    if len(df):
        try:
            top_idx = chg.idxmax()
            summary["top_name"] = _safe_str(df.loc[top_idx, name_c])
            summary["top_chg"] = _to_float(chg.loc[top_idx])
        except Exception:  # noqa: BLE001
            pass

    data = {
        "concepts": concepts,
        "summary": summary,
        "lifecycle_counts": life_counts,
        "unavailable": [],
    }
    return ok(data=_sanitize(data), message="theme")


@bp.get("/theme-transmission")
@jwt_required
def theme_transmission():
    """题材事件传导图谱（75 页 ④，按需触发）。抓取近期新闻标题 → 命中概念 → 展开成分股共现排序。

    复用 modules.news.EventMiner + modules.event_graph。取不到标题/概念→status='unavailable'，
    不编臆造题材表；任何异常→仍 200、status='unavailable'，不 500。
    """
    try:
        from modules.news import EventMiner
        from modules import event_graph as evg

        limit = _fa_int(request.args.get("limit"), 60, 1, 200)
        df = EventMiner().mine_events(limit=limit, auto_save=False)
        if df is None or getattr(df, "empty", True):
            return ok(data=_sanitize({
                "status": "unavailable",
                "reason": "未取到任何新闻标题（网络不可用或新闻接口异常）",
                "entries": [], "concepts_hit": [], "members_unavailable": [],
                "n_titles": 0, "n_concepts": 0,
            }), message="theme-transmission")

        titles = []
        for _, r in df.iterrows():
            title = str(r.get("title") or "").strip()
            if title:
                titles.append(title)
        if not titles:
            return ok(data=_sanitize({
                "status": "unavailable",
                "reason": "未取到任何新闻标题",
                "entries": [], "concepts_hit": [], "members_unavailable": [],
                "n_titles": 0, "n_concepts": 0,
            }), message="theme-transmission")

        idx = evg.build_index_for_titles(titles)
        res = evg.build_transmission(titles, idx)
        data = {
            "status": res.get("status", "empty"),
            "basis": res.get("basis"),
            "disclaimer": res.get("disclaimer"),
            "entries": res.get("entries") or [],
            "concepts_hit": res.get("concepts_hit") or [],
            "members_unavailable": res.get("members_unavailable") or [],
            "n_titles": len(titles),
            "n_concepts": len(idx),
        }
        return ok(data=_sanitize(data), message="theme-transmission")
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning("[theme] transmission failed: %s", e)
        return ok(data=_sanitize({
            "status": "unavailable",
            "reason": f"生成失败：{e}",
            "entries": [], "concepts_hit": [], "members_unavailable": [],
            "n_titles": 0, "n_concepts": 0,
        }), message="theme-transmission")


@bp.get("/strong")
@jwt_required
def strong():
    """实时强势榜只读聚合（76 页 V2 化）。复用 modules.spot_rank.load_spot_with_source + strong_score。

    返回全市场多因子强势评分（涨幅 0.40 + 量比 0.30 + 换手 0.20 + 成交额 0.10，启发式加权、非预测）；
    按 score 降序输出全部已评分标的（前端再按 top_n / 仅上涨 过滤）。二道闸（scan_and_gate 六维排雷）
    仅对评分 Top 200 候选排雷（控制六维扫描成本，与 v1 全量排雷略有差异），失败→kicked=[] 降级放行。

    红线：取不到快照→仍 200、unavailable=['spot_unavailable']、items=[]，不 500、不编数据；
    计算异常→仍 200、unavailable=['strong_compute_failed']。date=null（实时快照无历史数据日，绝不 now()）。
    """
    try:
        from modules import spot_rank as sr
        raw, src_label = sr.load_spot_with_source()
    except Exception:  # noqa: BLE001 - 取数层已内部降级，这里兜底
        raw, src_label = None, "不可用"

    if raw is None or getattr(raw, "empty", True):
        data = {
            "items": [],
            "src_label": "不可用",
            "kicked": [],
            "unavailable": ["spot_unavailable"],
            "date": None,
        }
        return ok(data=_sanitize(data), message="strong")

    try:
        scored = sr.strong_score(raw)
        code_c = sr._col(scored, "code")
        name_c = sr._col(scored, "name")
        price_c = sr._col(scored, "price")
        chg_c = sr._col(scored, "chg")
        amount_c = sr._col(scored, "amount")
        turnover_c = sr._col(scored, "turnover")
        vr_c = sr._col(scored, "vol_ratio")

        # 二道闸：六维排雷（仅评分 Top 200 候选，控制扫描成本；失败降级放行）
        kicked_codes: set = set()
        kicked_names: list = []
        try:
            from modules.risk_gate import scan_and_gate
            cand = scored.sort_values("_score", ascending=False).head(200)
            cand_list = [
                {"code": str(r.get(code_c, "")), "name": str(r.get(name_c, ""))}
                for _, r in cand.iterrows()
                if code_c
            ]
            if cand_list:
                _gated, summary = scan_and_gate(cand_list, top_k=len(cand_list))
                for k in (summary.get("kicked") or []):
                    kicked_codes.add(str(k.get("code")))
                    kicked_names.append(_safe_str(k.get("name")))
        except Exception:  # noqa: BLE001 - 二道闸失败：降级放行，不阻断榜单
            kicked_codes = set()
            kicked_names = []

        items = []
        rank = 0
        for _, r in scored.sort_values("_score", ascending=False).iterrows():
            code = str(r.get(code_c, "")) if code_c else ""
            if code in kicked_codes:
                continue
            rank += 1
            items.append({
                "rank": rank,
                "code": _safe_str(r.get(code_c)) if code_c else None,
                "name": _safe_str(r.get(name_c)) if name_c else None,
                "price": _to_float(r.get(price_c)) if price_c else None,
                "chg": _to_float(r.get(chg_c)) if chg_c else None,
                "amount": _to_float(r.get(amount_c)) if amount_c else None,
                "turnover": _to_float(r.get(turnover_c)) if turnover_c else None,
                "vol_ratio": _to_float(r.get(vr_c)) if vr_c else None,
                "score": _to_float(r.get("_score")),
                "s_chg": _to_float(r.get("_s_chg")),
                "s_vr": _to_float(r.get("_s_vr")),
                "s_to": _to_float(r.get("_s_to")),
                "s_amt": _to_float(r.get("_s_amt")),
            })

        data = {
            "items": items,
            "src_label": _safe_str(src_label) if src_label else "不可用",
            "kicked": kicked_names,
            "unavailable": [],
            "date": None,
        }
        return ok(data=_sanitize(data), message="strong")
    except Exception as e:  # noqa: BLE001 - 计算异常：诚实降级，不 500
        logging.getLogger(__name__).warning("[strong] 计算失败: %s", e)
        return ok(data=_sanitize({
            "items": [],
            "src_label": _safe_str(src_label) if src_label else "不可用",
            "kicked": [],
            "unavailable": ["strong_compute_failed"],
            "date": None,
        }), message="strong")


# ───────── 数据源 / 接口检测（diagnostics）─────────
# 与 W4-B/W4-C/W4-X 同款红线：@jwt_required + 统一 ok() 信封；只读、绝不写任何数据文件；
# 各检测项独立降级（任一失败只影响该项，不整页 500、不连带其它项）；缺失为 null、绝不补 0；
# 默认**零网络请求**（秒回，离线可用），仅 probe=1 时显式真实探网（旧版 93 页同款口径）。
#
# ⚠️ 刻意不用 data_health.health_rows_enriched()：其 detect_stall() 内部会
#    _ensure_health_table() → CREATE TABLE / CREATE INDEX（写库），违反本蓝图只读契约，
#    且会与在跑的后端服务抢 SQLite 锁。这里改用纯读的 health_rows()。
#
# 接口清单不硬编码：从 current_app.url_map 动态枚举 /api/v2/read/* 的 GET 规则，
# 保证新增/下线端点时清单自动同步（前端据此逐个真实 GET 探测，端到端验证）。
_DIAG_NOTE = (
    "数据源检测只读本地文件与缓存库（默认不触网）；接口检测由前端对真实注册端点逐个发起 "
    "GET 请求并记录 HTTP 状态与耗时。任一检测失败如实标注，不做成功假定、不补 0。"
)


def _diag_source_health():
    """依赖可用性 + 本地缓存表/行数：复用 fetcher 的 data_source_health()（静态、零网络）。

    失败整项降级为 {'available': False, ...}，绝不编造「全部可用」。
    """
    try:
        from ..api.market_routes import get_fetcher
        report = get_fetcher().data_source_health()
    except Exception as e:  # noqa: BLE001
        return {
            "available": False,
            "summary": None,
            "checked_at": None,
            "items": [],
            "reason": f"{type(e).__name__}: {e}"[:200],
        }
    items = []
    for key, info in (report.get("sources") or {}).items():
        if not isinstance(info, dict):
            continue
        items.append({
            "key": key,
            "label": info.get("label") or key,
            "ok": bool(info.get("ok")),
            "detail": info.get("detail"),
            "tables": info.get("tables"),
        })
    return {
        "available": True,
        "summary": report.get("summary"),
        "checked_at": report.get("timestamp"),
        "items": items,
        "reason": None,
    }


def _diag_freshness():
    """各决策数据源真实数据截止日 / 滞后天数 / 状态（纯读本地文件，不写库）。"""
    try:
        from modules.data_health import health_rows
        rows = health_rows()
    except Exception as e:  # noqa: BLE001
        return {
            "available": False,
            "rows": [],
            "reason": f"{type(e).__name__}: {e}"[:200],
        }
    return {"available": True, "rows": rows, "reason": None}


# 这些只读 GET 端点缺少 query 参数会直接 400 validation_error。
# 早期 _diag_endpoints 只按 "<" 判断参数需求，把它们当成「可直接探测」，
# 接真实后端时接口检测约 10 个端点假报 HTTP 400、数据浏览器一选就报错。
# 单一真理源：新增需参端点必须登记在这里（tests/test_diagnostics_endpoint_contract.py 会扫）。
_DIAG_REQUIRED_QUERY = {
    "/api/v2/read/paper-trades": {"user": "admin"},
    "/api/v2/read/review-notes": {"date": "2026-09-21"},
    "/api/v2/read/six-dim": {"code": "600519"},
    "/api/v2/read/fundamentals": {"code": "600519"},
    "/api/v2/read/financials": {"code": "600519"},
    "/api/v2/read/stock-kline": {"code": "600519"},
    "/api/v2/read/compare-one": {"code": "600519"},
    "/api/v2/read/research-deep": {"code": "600519"},
    "/api/v2/read/stock-intraday": {"code": "600519"},
    "/api/v2/read/index-kline": {"code": "sh000001"},
    # backtest 缺 ticker 即 fail(400, invalid_param)；必须登记，否则诊断探测会假报 400。
    "/api/v2/read/backtest": {"ticker": "600519"},
}


def _diag_endpoints():
    """从 Flask url_map 动态枚举只读 GET 端点。

    needs_params 覆盖路径参数（<...>）与必填 query 参数两类；需参端点
    probe_path=None（不自动探测），并带 required_query / sample_query 供
    数据浏览器生成输入框与合法示例值（示例值不是真实业务数据，UI 会标注）。
    """
    from flask import current_app
    out = []
    for rule in current_app.url_map.iter_rules():
        path = rule.rule
        if not path.startswith("/api/v2/read/") or "GET" not in (rule.methods or set()):
            continue
        params = _DIAG_REQUIRED_QUERY.get(path, {})
        has_path_param = "<" in path
        required = (["<path>"] if has_path_param else []) + sorted(params)
        needs_params = bool(required)
        sample_query = "&".join(f"{k}={v}" for k, v in params.items()) if params else None
        out.append({
            "path": path,
            "needs_params": needs_params,
            "probe_path": None if needs_params else path,
            "required_query": required,
            "sample_query": sample_query,
        })
    return sorted(out, key=lambda x: x["path"])


def _diag_network_probe():
    """四源真实网络探测：仅 probe=1 显式触发，复用 fetcher 的 realtime_probe 能力。"""
    try:
        from ..api.market_routes import get_fetcher
        report = get_fetcher().data_source_health(realtime_probe=True)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "levels": [],
                "reason": f"{type(e).__name__}: {e}"[:200]}
    probe = report.get("probe") or {}
    if probe.get("status") == "unavailable":
        return {"available": False, "levels": [], "reason": probe.get("reason")}
    levels = [
        {"level": lv, "ok": bool((info or {}).get("ok")),
         "detail": (info or {}).get("detail"),
         "latency_ms": (info or {}).get("latency_ms")}
        for lv, info in probe.items()
    ]
    return {"available": True, "levels": levels, "reason": None}


@bp.get("/diagnostics")
@jwt_required
def diagnostics():
    """数据源 + 接口检测数据。GET /api/v2/read/diagnostics[?probe=1]。

    默认零网络（秒回）；probe=1 时额外对四源各发一次真实日线请求（约数秒），
    结果放在 probe 字段，与旧版 93 页「真实网络探测」按钮同款口径。
    """
    want_probe = request.args.get("probe", "") in ("1", "true", "True")
    data = {
        "sources": _diag_source_health(),
        "freshness": _diag_freshness(),
        "endpoints": _diag_endpoints(),
        "probe": _diag_network_probe() if want_probe else None,
        "note": _DIAG_NOTE,
    }
    return ok(data=_sanitize(data), message="diagnostics")
