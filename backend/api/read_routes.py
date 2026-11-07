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
import math
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import fail, ok

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
    """每日荐股（data/daily_recommendation.json）—— 36 页主体数据源。"""
    return _serve_whitelist_json("daily_recommendation", "daily_recommendation.json")


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
