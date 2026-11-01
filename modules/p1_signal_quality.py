"""modules/p1_signal_quality.py —— P1 信号数据质量体检（方向 3：ks 信号数据质量监控自动化）。

用途
====
对 data/p1_signals/ 下现役信号文件做确定性体检，把隐性滞后变成显性告警：

  1. 结构体检：文件存在 / JSON 可解析 / 必备字段齐全 / top 榜数量 / symbol 格式 / rank 单调
  2. 新鲜度 SLA：latest_date 距今自然日 ≤ max_age_days（按模型可配）
  3. 跨模型对齐守望：ens 降权语义（w=0 应为纯 v39 序）——登记 ens vs baseline
     top 榜 Jaccard 重叠度，低于阈值亮黄灯（提示排查数据源版本错位 / gru 权重回归）
  4. 汇总：summarize() 扫目录出报告，全绿 ok_all=True

设计约束
========
  - 纯函数 + 显式传路径/日期，零网络零 IO 依赖（测试用 tmp 目录构造，不断言真实数据）。
  - 不读 modules.p1_signal，避免与加载器缓存/目录发现耦合，独立可测。
  - 阈值可配置：
      · DEFAULT_MAX_AGE_BY_MODEL（自然日，覆盖周末）——baseline/ev/gru/ens 8 天；
        fusion 30 天（2026-11-01 深挖：fusion 依赖 y_excess 前瞻标签，latest_date 设计性
        滞后约一个 h10 窗口+标签确认期，sj 推送链 S11 注释 T-352 为证——非事故，勿误报）。
      · ENS_MIN_JACCARD = 0.75：ens vs baseline top20 Jaccard 低于此值亮黄灯。
        2026-11-01 实测：0.652 → 亮黄灯；深挖结论：ens(w=0) 与 baseline v39 在 parquet 级
        同日 top20 Jaccard=1.0（无 gru 残留），黄灯根因是 baseline json 生成源
        pred_baseline_h10.parquet 与 ens 源 pred_baseline_h10_v39.parquet 模型版本不一致。
  - 三档语义：红灯 = 结构/新鲜度不达标（阻断）；黄灯 = 对齐异常（登记待核，不阻断）；
    绿灯 = 全达标。summarize().ok_all 仅被红灯影响。

背景（2026-11-01 方向 3 实测基线）
================================
  · signal_ens_v39gru_w025_h10.json generated 11-01 17:17（model=ens_v39gru_w025，latest=10-26）
    vs signal_baseline_h10.json（generated 10-27，latest=10-26）：top20 Jaccard=0.652，同名位 3/20。
    —— 深挖后根因：baseline json 生成源 pred_baseline_h10.parquet 与 ens 源
       pred_baseline_h10_v39.parquet 的同日 pred 值不一致（600212：0.0199 vs 0.0392；
       top20 Jaccard=0.667）→ baseline json 用的是非 v39 口径文件，需 sj 侧统一生产源。
  · signal_fusion_h10.json latest=2026-10-12（滞后 20 自然日）→ 设计性滞后（y_excess 前瞻标签），
    SLA 已单独放宽至 30 天；若未来停更超 30 天才视为异常。
  · logs/p1_push_heartbeat.log 最后心跳 2026-10-31 00:00:50 → 完整推送链未每日跑（另有推送链 SLA 治理项）。
"""
from __future__ import annotations

import json
import os
import re
from datetime import date

# ───────────────────────── 常量与默认阈值 ─────────────────────────
HEALTHY_KEYS = ("model", "latest_date", "horizon", "top_long", "top_short", "daily")

# 模型 key（短名，来自文件名前缀 signal_{prefix}_*.json）
# 注：fusion 依赖 y_excess 前瞻标签（sj 推送链 S11 注释，T-352），latest_date 设计性
#     滞后于四路（约一个 h10 窗口+标签确认期），故 SLA 单独放宽，勿与四路同口径。
DEFAULT_MAX_AGE_BY_MODEL = {
    "baseline": 8,
    "ev": 8,
    "gru": 8,
    "ens": 8,
    "fusion": 30,
}

# ens 降权语义守望阈值：ens vs baseline top20 Jaccard 低于此值 → 黄灯
# 注（2026-11-01 深挖结论）：ens(w=0) 的 pred=当日截面 z_v39，与 baseline v39 pred
#   在单日截面单调等价——parquet 级同日 top20 Jaccard=1.0（无 gru 残留）。黄灯若出现，
#   优先怀疑 baseline json 生成源文件（pred_baseline_h10.parquet）与 ens 源
#   （pred_baseline_h10_v39.parquet）模型版本不一致，而非 gru 权重回归。
ENS_MIN_JACCARD = 0.75

# 推送链心跳 SLA：完整推送链（S01~S13）应周期性运行，心跳文件最后 OK 行距今不超过该自然日数
DEFAULT_HEARTBEAT_MAX_IDLE_DAYS = 3

# 与 p1_signal.loader 对齐的模型显示名（仅用于报告可读性）
MODEL_LABELS = {
    "baseline": "基线 LightGBM",
    "ev": "EV 事件因子",
    "gru": "GRU 深度学习",
    "ens": "ens 集成(v39+gru)",
    "fusion": "条件融合",
}

_TOP_KEY_PATTERN = re.compile(r"^(sh|sz|bj)\d{6}$")


# ───────────────────────── 纯函数体检 ─────────────────────────
def extract_model_key(filename: str) -> str | None:
    """从文件名提取模型短键：signal_{prefix}_h10.json → prefix；非信号文件 → None。

    兼容前缀内带下划线的命名（如 signal_ens_v39gru_w025_h10.json → ens）。
    """
    base = os.path.basename(filename)
    if not base.startswith("signal_") or not base.endswith(".json"):
        return None
    inner = base[len("signal_"):-len(".json")]
    # 去掉 horizon 后缀（_h10/_h20/...），剩余部分的首段即模型键
    for suffix in ("_h10", "_h20", "_h5", "_h15"):
        if inner.endswith(suffix):
            inner = inner[: -len(suffix)]
            break
    key = inner.split("_")[0]
    if key == "ens":
        return "ens"
    if key in DEFAULT_MAX_AGE_BY_MODEL:
        return key
    return key  # 未知模型也返回，便于报告展示


def is_valid_symbol(sym: str) -> bool:
    return bool(_TOP_KEY_PATTERN.match(sym or ""))


def age_days(latest_date: str, today: date | None = None) -> int | None:
    """latest_date 距今自然日差。非法/缺失 → None（不编造）；未来日期钳 0。"""
    if not latest_date:
        return None
    try:
        d = date.fromisoformat(str(latest_date)[:10])
    except (ValueError, TypeError):
        return None
    base = today or date.today()
    return max((base - d).days, 0)


def _check_rank_monotonic(rows, ascending: bool = False) -> bool:
    """top_long：rank 应非增（1.0 最强在前）；top_short：rank 应非降（最小=最强看空在前）。"""
    ranks = [r.get("rank") for r in rows if isinstance(r, dict) and "rank" in r]
    for a, b in zip(ranks, ranks[1:]):
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        if ascending:
            if a - 1e-9 > b:
                return False
        elif a + 1e-9 < b:
            return False
    return True


def check_file(path: str, model_key: str | None = None, today: date | None = None,
               max_age: int | None = None) -> dict:
    """单文件结构 + 新鲜度体检。红灯不达标项在 errors 中列出。

    返回字段：ok / file / exists / parseable / missing_keys / n_top_long / n_top_short /
              n_daily / latest_date / age_days / freshness_ok / symbol_ok / rank_ok / errors
    """
    rec = {
        "file": os.path.basename(path),
        "model_key": model_key,
        "ok": False,
        "exists": False,
        "parseable": False,
        "missing_keys": [],
        "n_top_long": 0,
        "n_top_short": 0,
        "n_daily": 0,
        "latest_date": None,
        "age_days": None,
        "freshness_ok": False,
        "symbol_ok": True,
        "rank_ok": True,
        "errors": [],
    }
    if not os.path.exists(path):
        rec["errors"].append("文件不存在")
        return rec
    rec["exists"] = True

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        rec["errors"].append(f"JSON 解析失败: {type(e).__name__}")
        return rec
    if not isinstance(data, dict):
        rec["errors"].append("顶层不是 JSON 对象")
        return rec
    rec["parseable"] = True

    missing = [k for k in HEALTHY_KEYS if k not in data]
    rec["missing_keys"] = missing
    if missing:
        rec["errors"].append("缺字段: " + ",".join(missing))

    top_long = data.get("top_long", []) if isinstance(data.get("top_long"), list) else []
    top_short = data.get("top_short", []) if isinstance(data.get("top_short"), list) else []
    daily = data.get("daily", []) if isinstance(data.get("daily"), list) else []
    rec["n_top_long"], rec["n_top_short"], rec["n_daily"] = len(top_long), len(top_short), len(daily)

    if top_long:
        rec["rank_ok"] = rec["rank_ok"] and _check_rank_monotonic(top_long, ascending=False)
        for r in top_long:
            if isinstance(r, dict) and not is_valid_symbol(str(r.get("symbol", ""))):
                rec["symbol_ok"] = False
                break
    if top_short:
        rec["rank_ok"] = rec["rank_ok"] and _check_rank_monotonic(top_short, ascending=True)
        for r in top_short:
            if isinstance(r, dict) and not is_valid_symbol(str(r.get("symbol", ""))):
                rec["symbol_ok"] = False
                break
    if not rec["symbol_ok"]:
        rec["errors"].append("symbol 格式非法（应为 sh/sz/bj + 6 位数字）")
    if not rec["rank_ok"]:
        rec["errors"].append("rank 排序异常（看多榜应非增、看空榜应非降）")

    latest = data.get("latest_date")
    rec["latest_date"] = latest
    age = age_days(latest, today)
    rec["age_days"] = age
    if age is None:
        rec["errors"].append("latest_date 缺失或非法 ISO 日期")
    else:
        limit = max_age if max_age is not None else DEFAULT_MAX_AGE_BY_MODEL.get(model_key, 8)
        rec["freshness_ok"] = age <= limit
        if not rec["freshness_ok"]:
            rec["errors"].append(f"数据滞后 {age} 自然日（SLA ≤ {limit}）")

    rec["ok"] = not rec["errors"]
    return rec


# ───────────────────────── 跨模型对齐守望 ─────────────────────────
def top_symbols(data: dict, n: int = 20) -> list:
    rows = data.get("top_long", []) if isinstance(data.get("top_long"), list) else []
    return [str(r.get("symbol", "")) for r in rows[:n] if isinstance(r, dict) and r.get("symbol")]


def jaccard(a: list, b: list) -> float:
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def check_ens_baseline_alignment(ens_path: str, baseline_path: str, n: int = 20,
                                 min_jaccard: float = ENS_MIN_JACCARD) -> dict:
    """ens 降权语义守望：登记 ens vs baseline top 榜重叠度。

    - aligned=True（绿）：重叠度 ≥ 阈值 → ens 与基线高一致，降权语义成立。
    - aligned=False（黄灯）：低于阈值 → 提示排查 gru 权重回归 / z 序口径 / 数据版本错位。
      黄灯不阻断（ok=True），但会显式登记 jaccard 供人工核对。
    - 任一文件缺失/不可解析 → status="unavailable"，不判黄灯。
    """
    rec = {"status": "ok", "ok": True, "aligned": True, "jaccard": None,
           "shared": 0, "n": n, "min_jaccard": min_jaccard, "note": ""}
    for label, p in (("ens", ens_path), ("baseline", baseline_path)):
        try:
            with open(p, encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            rec["status"] = "unavailable"
            rec["note"] = f"{label} 文件缺失或不可解析，无法比对"
            return rec
    a = top_symbols(json.load(open(ens_path, encoding="utf-8")), n)
    b = top_symbols(json.load(open(baseline_path, encoding="utf-8")), n)
    rec["jaccard"] = jaccard(a, b)
    rec["shared"] = len(set(a) & set(b))
    rec["aligned"] = rec["jaccard"] >= min_jaccard
    if not rec["aligned"]:
        rec["ok"] = True  # 黄灯不阻断
        rec["note"] = (f"黄灯：ens vs baseline top{n} Jaccard={rec['jaccard']:.3f} "
                       f"< {min_jaccard}——疑似 baseline json 源(pred_baseline_h10.parquet)与 "
                       f"ens 源(pred_baseline_h10_v39.parquet)模型版本不一致，需 sj 侧核对生产口径")
    return rec


# ───────────────────────── 推送链心跳体检 ─────────────────────────
def check_heartbeat(path: str, today: date | None = None,
                    max_idle_days: int | None = None) -> dict:
    """推送链心跳体检：文件存在、最后一行含 OK 标记、mtime 新鲜度。

    语义：完整推送链（S01~S13）每步会写心跳日志；若心跳文件停止更新，
    说明推送链断供——页面数据可能停留在旧版本。红灯 = 结构或新鲜度不达标。
    """
    rec = {"ok": False, "exists": False, "last_ok": False, "last_line": None,
           "idle_days": None, "idle_ok": False, "errors": []}
    if not os.path.exists(path):
        rec["errors"].append("心跳文件不存在")
        return rec
    rec["exists"] = True

    last_line = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()
    except OSError as e:
        rec["errors"].append(f"心跳文件读取失败: {type(e).__name__}")
        return rec
    rec["last_line"] = last_line
    rec["last_ok"] = "OK" in last_line
    if not rec["last_ok"]:
        rec["errors"].append(f"心跳最后一行无 OK 标记: {last_line!r}")

    mtime = os.path.getmtime(path)
    idle = max((today or date.today()).toordinal() - date.fromtimestamp(mtime).toordinal(), 0)
    rec["idle_days"] = idle
    limit = max_idle_days if max_idle_days is not None else DEFAULT_HEARTBEAT_MAX_IDLE_DAYS
    rec["idle_ok"] = idle <= limit
    if not rec["idle_ok"]:
        rec["errors"].append(f"推送链心跳停更 {idle} 天（SLA ≤ {limit}）")

    rec["ok"] = not rec["errors"]
    return rec


# ───────────────────────── 目录汇总 ─────────────────────────
def summarize(signal_dir: str, today: date | None = None,
              max_age_by_model: dict | None = None,
              ens_min_jaccard: float = ENS_MIN_JACCARD,
              heartbeat_path: str | None = None,
              heartbeat_max_idle_days: int | None = None) -> dict:
    """扫描信号目录，输出全量体检报告。ok_all = 所有红灯项为零（黄灯不阻断）。

    heartbeat_path 传入时额外体检推送链心跳；缺省 None 跳过（不阻断目录扫描）。
    """
    max_ages = {**DEFAULT_MAX_AGE_BY_MODEL, **(max_age_by_model or {})}
    rows = []
    ok_all = True
    models_found = []
    if os.path.isdir(signal_dir):
        for name in sorted(os.listdir(signal_dir)):
            if not name.startswith("signal_") or name.endswith(".json") is False:
                continue
            if ".bak" in name:
                continue
            key = extract_model_key(name)
            if key:
                models_found.append(key)
            rec = check_file(os.path.join(signal_dir, name), model_key=key, today=today,
                             max_age=max_ages.get(key))
            if not rec["ok"]:
                ok_all = False
            rows.append(rec)

    alignment = None
    ens_file = next((os.path.join(signal_dir, n) for n in os.listdir(signal_dir)
                     if n.startswith("signal_ens") and n.endswith(".json") and ".bak" not in n), None)
    base_file = next((os.path.join(signal_dir, n) for n in os.listdir(signal_dir)
                      if n.startswith("signal_baseline") and n.endswith(".json") and ".bak" not in n), None)
    if ens_file and base_file:
        alignment = check_ens_baseline_alignment(ens_file, base_file, min_jaccard=ens_min_jaccard)

    heartbeat = None
    if heartbeat_path:
        heartbeat = check_heartbeat(heartbeat_path, today=today,
                                    max_idle_days=heartbeat_max_idle_days)
        if not heartbeat["ok"]:
            ok_all = False

    return {
        "ok_all": ok_all,
        "rows": rows,
        "alignment": alignment,
        "heartbeat": heartbeat,
        "models_found": sorted(set(models_found)),
        "signal_dir": signal_dir,
        "today": (today or date.today()).isoformat(),
    }


# ───────────────────────── 报告渲染 ─────────────────────────
def render_report(summary: dict) -> str:
    """把 summarize() 结果渲染为人类可读报告（Markdown 表格）。"""
    lines = []
    lines.append(f"# P1 信号数据质量体检 — {summary['today']}")
    lines.append("")
    lines.append(f"- 目录: `{summary['signal_dir']}`")
    lines.append(f"- 发现模型: {', '.join(summary['models_found']) or '（无）'}")
    lines.append("")
    lines.append("| 文件 | 模型 | 结构 | 新鲜度 | latest_date | 滞后(天) | top_long | top_short | 问题 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in summary["rows"]:
        struct = "✅" if r["ok"] else "❌"
        fresh = "✅" if r.get("freshness_ok") else ("⚠️" if r.get("age_days") is not None else "❌")
        problems = "; ".join(r["errors"]) if r["errors"] else "—"
        lines.append(
            f"| {r['file']} | {r['model_key'] or '?'} | {struct} | {fresh} | "
            f"{r['latest_date'] or '—'} | {r['age_days'] if r['age_days'] is not None else '—'} | "
            f"{r['n_top_long']} | {r['n_top_short']} | {problems} |"
        )
    lines.append("")
    if summary["heartbeat"] is not None:
        hb = summary["heartbeat"]
        if hb["exists"]:
            state = "✅" if hb["ok"] else "❌"
            lines.append(f"**推送链心跳**：{state} 最后 OK 行距今 {hb['idle_days']} 天")
            if hb["errors"]:
                lines.append(f"  - 问题: {'; '.join(hb['errors'])}")
        else:
            lines.append(f"**推送链心跳**：❌ {hb['errors'][0] if hb['errors'] else '文件缺失'}")
        lines.append("")
    if summary["alignment"] is not None:
        al = summary["alignment"]
        if al["status"] == "unavailable":
            lines.append(f"**ens↔baseline 对齐守望**：{al['note']}")
        elif al["aligned"]:
            lines.append(f"**ens↔baseline 对齐守望**：✅ Jaccard={al['jaccard']:.3f}（≥ {al['min_jaccard']}）降权语义成立")
        else:
            lines.append(f"**ens↔baseline 对齐守望**：{al['note']}")
        lines.append("")
    lines.append(f"**结论**：{'✅ 全绿（红灯项为零）' if summary['ok_all'] else '❌ 存在红灯项，需处理'}（黄灯登记不阻断）")
    return "\n".join(lines)
