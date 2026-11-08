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

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import fail, ok

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
    """递归剔除敏感 key（默认 target_dir），防本机绝对路径随响应泄露。

    p1_sync_status.json 的 target_dir 是 'E:\\\\...\\\\data\\\\p1_signals'，
    属部署环境信息，不应出现在浏览器可见的 API 响应里；嵌套在 dict / list
    内的同名 key 一并剔除。该函数只删 key，不改写任何值。
    """
    banned = banned_keys or {"target_dir"}
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
    df, _prev_close, trade_date = got if isinstance(got, tuple) and len(got) == 3 else (None, None, None)
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
        "note": _W4C_NOTE + "；分时底层复用 get_stock_intraday_sina（新浪分钟K线），缺失->rows=[]、date=null，绝不编造",
    }
    return ok(data=_sanitize(data), message="stock-intraday")
