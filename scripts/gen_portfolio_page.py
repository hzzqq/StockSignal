"""生成 StockSignal 作品集主页（单文件 HTML，图片 base64 内嵌，离线双击即开）。

为什么要这个脚本（而不是手写 HTML）：
1. **数字必须是真的**——所有规模指标从仓库实时算出（文件数/行数/提交数/数据行数），
   避免"README 写 1767 个测试、实际 2608"这类自降身价的陈旧数字。
   **硬编码禁令**：模板里不得再写死任何规模数字（页数/端点数/测试数/模块数），
   一律走 @占位符@。本文件就曾同时出现 "2608" 与 "2,648" 两个互相矛盾的测试数、
   以及写死的 "41 个功能页面 / 76 个端点 / 77 业务模块"，全部已改为占位符；
   由 tests/test_public_numbers_consistency.py 静态守住。
   **图注必须与图片一致**：作品集页曾把 thesis/ch6_eval/fig_history_trend.png（实际内容是
   「评估数据累积趋势（每次运行 +1）」）写成「15 年全市场广度历史（4094 交易日）」——
   典型「图注与图不符」。现已由 scripts/gen_breadth_history_fig.py 从
   data/shepherd_history.csv 产出真图（docs/assets/fig_breadth_history.png），
   其余三张图注亦改为按图实述。
2. **图片内嵌**——发给 HR 的是一个文件，不会出现「图片裂了」。
3. **可重跑**——每次迭代后重跑一次，门面永远与代码同步。

用法：
    python scripts/gen_portfolio_page.py            # 自动采集（含 pytest 收集测试数）
    python scripts/gen_portfolio_page.py --fast     # 跳过 pytest（用 AST 计数，秒出）

输出：docs/index.html（GitHub Pages「main / docs」可直接作为站点首页）
"""
from __future__ import annotations

import argparse
import ast
import base64
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
OUT = os.path.join(ROOT, "docs", "index.html")

PY = sys.executable


# ─────────────────────────── 真实指标采集 ───────────────────────────
def _lines(paths: list[str]) -> int:
    total = 0
    for p in paths:
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                total += sum(1 for _ in f)
        except OSError:
            continue
    return total


def _walk(sub: str, suffix: str = ".py") -> list[str]:
    out = []
    base = os.path.join(ROOT, sub)
    for dirpath, _dirs, files in os.walk(base):
        if "__pycache__" in dirpath:
            continue
        for fn in files:
            if fn.endswith(suffix):
                out.append(os.path.join(dirpath, fn))
    return out


def _count_routes() -> int:
    """生产 REST 路由装饰器数（**排除 backend/tests**）。

    实测口径：本函数结果必须与 Flask ``app.url_map`` 的非 static 规则数一致（当前 75）。
    曾经漏排 tests 目录，把 ``backend/tests/test_security.py`` 里的测试专用路由
    ``/api/_test_boom`` 也算了进去 → 对外多报 1 个端点（76）。
    """
    n = 0
    pat = re.compile(r"@[A-Za-z_]+\.(route|get|post|put|delete|patch)\(")
    for p in _walk("backend"):
        if "tests" in os.path.relpath(p, ROOT).split(os.sep):
            continue
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                n += len(pat.findall(f.read()))
        except OSError:
            continue
    return n


def _ast_test_count() -> int:
    """AST 数 def test_*（不导入模块，秒出）。"""
    n = 0
    for p in _walk("tests") + _walk("backend/tests"):
        try:
            tree = ast.parse(open(p, encoding="utf-8", errors="ignore").read())
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                n += 1
    return n


def _pytest_count() -> int | None:
    """真实「用例数」（含 parametrize 展开）——这是对外引用时应报的口径。"""
    try:
        r = subprocess.run(
            [PY, "-m", "pytest", "tests", "backend/tests", "--collect-only", "-q", "-p", "no:cacheprovider"],
            cwd=ROOT, capture_output=True, text=True, timeout=900,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    total = 0
    for line in r.stdout.splitlines():
        m = re.match(r"^(?:tests|backend)/.*: (\d+)$", line.strip())
        if m:
            total += int(m.group(1))
    return total or None


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _git_days() -> int:
    out = _git("log", "--format=%ad", "--date=short")
    return len({ln for ln in out.splitlines() if ln})


def _csv_rows(rel: str) -> int:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return 0
    with open(p, encoding="utf-8-sig", errors="ignore") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _csv_span(rel: str, col: int = 0, sep: str = "–") -> str:
    """从 CSV 首/末有效行推导覆盖区间标签（如 '2007–2026'）；无数据返回空串。"""
    import csv as _csv
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return ""
    first = last = ""
    try:
        with open(p, encoding="utf-8-sig", errors="ignore", newline="") as f:
            r = _csv.reader(f)
            next(r, None)
            for row in r:
                if not row:
                    continue
                v = (row[col] or "").strip()
                if not v:
                    continue
                if not first:
                    first = v
                last = v
    except OSError:
        return ""
    if not first or not last:
        return ""
    return f"{first[:4]}{sep}{last[:4]}"


def _backtest_stats() -> dict:
    """回测权威口径（reports/backtest_decision_closure.json）；缺失时全 0，不猜。"""
    import json as _json
    p = os.path.join(ROOT, "reports", "backtest_decision_closure.json")
    zero = {"scored": 0, "call": 0, "hit": 0, "acc": 0.0}
    if not os.path.exists(p):
        return zero
    try:
        d = _json.loads(open(p, encoding="utf-8").read())
    except (OSError, ValueError):
        return zero
    o = d.get("overall") or {}
    m = d.get("meta") or {}
    return {
        "scored": int(m.get("n_trading_days_scored") or o.get("n") or 0),
        "call": int(o.get("call") or 0),
        "hit": int(o.get("hit") or 0),
        "acc": float(o.get("dir_accuracy") or 0.0),
    }


def _glob_count(sub: str, suffix: str = ".py") -> int:
    base = os.path.join(ROOT, sub)
    if not os.path.isdir(base):
        return 0
    return len([f for f in os.listdir(base) if f.endswith(suffix)])


def _guard_test_files() -> int:
    """含 AST 源码级护栏的测试文件数（工程纪律的硬证据）。"""
    n = 0
    for p in _walk("tests"):
        try:
            src = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if "ast.parse" in src and "assert" in src:
            n += 1
    return n


def collect(fast: bool = False) -> dict:
    src_paths = _walk("modules") + _walk("pages") + _walk("backend")
    src_paths = [p for p in src_paths if os.sep + "tests" + os.sep not in p]
    test_paths = _walk("tests") + _walk("backend/tests")

    tests = None if fast else _pytest_count()
    hist = _git("log", "--reverse", "--format=%ad", "--date=short").splitlines()

    stats = {
        "pages": _glob_count("pages"),
        "modules": _glob_count("modules"),
        "routes": _count_routes(),
        "py_files": len(_walk(".")),
        "src_loc": _lines(src_paths) + _lines([os.path.join(ROOT, "app.py")]),
        "test_loc": _lines(test_paths),
        "test_files": len([p for p in test_paths if os.path.basename(p).startswith("test")]),
        "tests": tests or _ast_test_count(),
        "tests_exact": tests is not None,
        "guards": _guard_test_files(),
        "commits": int(_git("rev-list", "--count", "HEAD") or 0),
        "days": _git_days(),
        "first_day": hist[0] if hist else "",
        "last_day": hist[-1] if hist else "",
        "breadth_days": _csv_rows("data/shepherd_history.csv"),
        "breadth_span": _csv_span("data/shepherd_history.csv"),
        "bt": _backtest_stats(),
        "stocks": len([f for f in os.listdir(os.path.join(ROOT, "data", "shepherd_cache_v2"))
                       if f.endswith(".csv")]) if os.path.isdir(
            os.path.join(ROOT, "data", "shepherd_cache_v2")) else 0,
    }
    return stats


# ─────────────────────────── 资源内嵌 ───────────────────────────
def _data_uri(rel: str) -> str:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return ""
    mime = "image/png" if rel.lower().endswith(".png") else "image/jpeg"
    with open(p, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")


SHOTS = [
    ("screenshots/01-kline-light.png", "行情看板 · 日K + 4 均线 + 量能", "亮色主题"),
    ("screenshots/02-kline-dark.png", "暗夜主题 · starfield_dark 模板", "双主题"),
    ("screenshots/03-sector-heatmap.png", "板块热力图 · 行业涨跌分布", "A股红涨绿跌"),
    ("screenshots/04-multi-stock-compare.png", "多股对比 · 5 只蓝筹归一化", "一次多标的"),
    # 这张图曾经是 scripts/gen_screenshots.py 用随机数编造的"策略跑赢基准"曲线，
    # 后又退化成一张报错占位图。现已改为真实回测引擎跑出的成本 A/B 对照（见该脚本
    # shot_backtest_curve 的说明），标题必须如实描述，不得再写"vs 沪深300"。
    ("screenshots/05-backtest-curve.png", "回测引擎 · 成本模型 A/B 对照",
     "含佣金/印花税/滑点 vs 零成本，摩擦拖累 3.99pp"),
    ("screenshots/06-signal-radar.png", "信号评分雷达 · 价格 / 事件 / 宏观",
     "真实 K 线 + 事件库打分，非示意数据"),
]

CHARTS = [
    # 图 1：真·广度历史图（scripts/gen_breadth_history_fig.py 从真实 CSV 产出）。
    # 曾误把 thesis/ch6_eval/fig_history_trend.png（实为「评估数据累积趋势」）当成广度历史图。
    ("docs/assets/fig_breadth_history.png",
     "A 股全市场广度历史（@BREADTH_SPAN@，@BREADTH@ 交易日）",
     "自己重建的数据基座：年度平均红盘率（柱）+ 日均涨跌家数（线），逐日广度指标完整、离线可复现。"),
    # 以下三张均为「每日自动落盘、次日回填」评估闭环的真实产物，图注按图实述。
    ("thesis/ch6_eval/fig_position.png", "决策闭环 · 每日仓位建议（clamp 5~95 校验）",
     "真实运行产出的每日仓位序列：输出恒落在 [5,95] 内（上下限虚线），随情绪定位逐日变化。"),
    ("thesis/ch6_eval/fig_temp_pos.png", "情绪温度 → 建议仓位（真实散点）",
     "温度与建议仓位的真实对应分布。样本仍在累积，故只呈现事实、不提前断言单调性。"),
    ("thesis/ch6_eval/fig_hit_trend.png", "预测 vs 实际：预测仓位与次日实际涨跌",
     "蓝=预测仓位(%)，红=次日实际涨跌(%)，绿/红点=命中/未中 —— 每日落盘、次日回填的真实评分链路。"),
]


# ─────────────────────────── HTML 模板 ───────────────────────────
CSS = """
:root{
  --bg:#0f0f23; --bg2:#141428; --card:#1a1a2e; --card2:#20203a;
  --line:#2a2a4a; --txt:#e8e8f4; --dim:#a0a0c0; --dim2:#7070a0;
  --grad:linear-gradient(135deg,#667eea,#764ba2);
  --up:#ff4d4f; --down:#00d486; --gold:#ffd166;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  line-height:1.7;-webkit-font-smoothing:antialiased}
.wrap{max-width:1160px;margin:0 auto;padding:0 28px}
a{color:#8fa8ff;text-decoration:none}
code{background:#00000055;border:1px solid var(--line);border-radius:6px;padding:2px 7px;
  font-family:"JetBrains Mono",Consolas,monospace;font-size:.88em;color:#a9c4ff}
.hero{padding:76px 0 52px;background:
  radial-gradient(1100px 460px at 12% -12%,rgba(102,126,234,.30),transparent 60%),
  radial-gradient(900px 420px at 92% -6%,rgba(118,75,162,.28),transparent 60%)}
.badge{display:inline-block;border:1px solid #667eea88;background:#667eea1f;color:#b9c8ff;
  border-radius:999px;padding:5px 15px;font-size:13px;letter-spacing:.4px;margin-bottom:20px}
h1{font-size:clamp(30px,4.4vw,50px);line-height:1.18;letter-spacing:-.5px;font-weight:800}
h1 .g{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--dim);font-size:clamp(15px,1.7vw,19px);margin-top:18px;max-width:900px}
.hero-tags{margin-top:26px;display:flex;flex-wrap:wrap;gap:10px}
.tag{border:1px solid var(--line);background:#ffffff08;border-radius:8px;padding:6px 13px;
  font-size:13.5px;color:var(--dim)}
section{padding:56px 0;border-top:1px solid var(--line)}
h2{font-size:clamp(21px,2.5vw,29px);font-weight:800;margin-bottom:10px;display:flex;align-items:center;gap:11px}
.lead{color:var(--dim);margin-bottom:30px;max-width:900px;font-size:15.5px}
.grid{display:grid;gap:16px}
.g4{grid-template-columns:repeat(auto-fit,minmax(205px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(285px,1fr))}
.g2{grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 20px;
  position:relative;overflow:hidden}
.stat::after{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:var(--grad)}
.stat .n{font-size:clamp(26px,3.2vw,36px);font-weight:800;letter-spacing:-1px;
  background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.stat .l{color:var(--dim);font-size:13.5px;margin-top:6px}
.stat .x{color:var(--dim2);font-size:12.5px;margin-top:3px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px}
.card h3{font-size:17.5px;margin-bottom:10px;display:flex;align-items:center;gap:9px}
.card p{color:var(--dim);font-size:14.5px}
.card.hl{border-color:#ffd16666;background:linear-gradient(180deg,#ffd1660f,transparent 60%),var(--card)}
.kicker{font-size:12.5px;color:var(--gold);letter-spacing:1.4px;text-transform:uppercase;margin-bottom:9px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
th,td{text-align:left;padding:11px 13px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim2);font-weight:600;font-size:12.5px;letter-spacing:.6px;text-transform:uppercase}
td.mono{font-family:"JetBrains Mono",Consolas,monospace;color:#a9c4ff;font-size:12.5px;white-space:nowrap}
figure{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
figure img{width:100%;display:block;background:#0b0b18}
figcaption{padding:14px 17px;font-size:13.5px;color:var(--dim)}
figcaption b{color:var(--txt);display:block;margin-bottom:4px;font-size:14.5px}
.shot figcaption span{color:var(--dim2);font-size:12.5px}
.arch{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:26px;
  font-family:"JetBrains Mono",Consolas,monospace;font-size:12.8px;color:#c3c3e0;
  white-space:pre;overflow-x:auto;line-height:1.75}
.stack{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}
.stack span{background:#ffffff0a;border:1px solid var(--line);border-radius:7px;
  padding:6px 12px;font-size:13px;color:var(--dim)}
.q{background:var(--card2);border-left:3px solid #667eea;border-radius:0 12px 12px 0;
  padding:17px 20px;margin-bottom:13px}
.q b{display:block;margin-bottom:7px;font-size:15px}
.q p{color:var(--dim);font-size:14.2px}
.cmd{background:#0a0a16;border:1px solid var(--line);border-radius:12px;padding:17px 19px;
  font-family:"JetBrains Mono",Consolas,monospace;font-size:13px;color:#9fe8c3;overflow-x:auto;white-space:pre}
footer{padding:44px 0 60px;border-top:1px solid var(--line);color:var(--dim2);font-size:13.5px;text-align:center}
.note{font-size:12.8px;color:var(--dim2);margin-top:12px}
@media(max-width:640px){.wrap{padding:0 18px}section{padding:40px 0}.hero{padding:52px 0 36px}}
"""

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockSignal · A股事件驱动投资分析平台 | 项目作品集</title>
<meta name="description" content="@PAGES@ 页 Streamlit + Flask 全栈平台，@TESTS@ 个自动化测试，基于 @BREADTH_SPAN@ 共 @BREADTH@ 个交易日的真实广度数据做全链路回测，并如实披露方向命中率≈随机。">
<style>@CSS@</style>
</head>
<body>

<header class="hero">
  <div class="wrap">
    <div class="badge">● 个人独立项目 · 全栈自研 · Python</div>
    <h1>StockSignal<br><span class="g">把「市场情绪」做成可回测、可自校准的仓位决策闭环</span></h1>
    <p class="sub">
      不是又一个「选股器」。这是一个把 <b>情绪周期定位 → 仓位推导 → 每日落盘预测 → 次日回填打分 → 分组刻度校准</b>
      串成闭环的 A 股分析平台：@PAGES@ 个功能页面、@ROUTES@ 个后端 REST 端点、@SRC_LOC@ 行自研源码、
      <b>@TESTS@ 个自动化测试</b>，并重建了覆盖 <b>@BREADTH_SPAN@ 共 @BREADTH@ 个交易日</b>的全市场广度数据基座。
    </p>
    <div class="hero-tags">
      <span class="tag">Streamlit + Flask 前后端分离</span>
      <span class="tag">4 源自动降级 + SQLite 缓存</span>
      <span class="tag">Backtrader 回测（含真实成本模型）</span>
      <span class="tag">@TESTS@ 项测试 · 含 AST 源码护栏</span>
      <span class="tag">诚实负向结论：方向命中率 @ACC@%</span>
    </div>
  </div>
</header>

<section>
  <div class="wrap">
    <h2>🎯 三个「别人简历上没有」的点</h2>
    <p class="lead">大部分同类项目停在「能跑、页面多」。这三个点是我把项目做深的地方，也是面试时最能展开聊的。</p>
    <div class="grid g3">
      <div class="card hl">
        <div class="kicker">诚实 / 可证伪</div>
        <h3>🔬 把「测不准」写进论文，而不是藏起来</h3>
        <p>用 @BT_DAYS@ 个可评分交易日的真实广度历史回测完整决策链路，得到方向命中率 <b>@ACC@%（@HIT@/@CALL@）≈ 随机</b>。
        我没有改口径去凑一个好看的数字，而是把它作为「能力边界」如实披露，并进一步定位到：
        这套系统的价值不在「猜次日涨跌」，而在<b>仓位刻度随市场状态缩放</b>。
        <b>结论可复现</b>：一条命令重跑全部数字。</p>
      </div>
      <div class="card">
        <div class="kicker">方法论 / 差异化</div>
        <h3>♻️ 闭环会自我纠偏，且给自己上了三道锁</h3>
        <p>仓位建议不是写死的经验常数，而是由回测分组统计反推的<b>刻度校准</b>模块驱动。
        为防止「用噪音拟合自己」，内置三条铁律：<b>① 只出建议、绝不自动改规则</b>；
        <b>② 调节量有界（±5）</b>；<b>③ 小样本不表态</b>（样本不足或调节量在噪音阈值内则明确「不动」）。</p>
      </div>
      <div class="card">
        <div class="kicker">工程纪律</div>
        <h3>🛡 测试不是走过场，是能抓真 bug 的护栏</h3>
        <p><b>@TESTS@ 个自动化测试</b>（@TEST_LOC@ 行测试代码）+ <b>@GUARDS@ 个文件</b>含源码级
        AST 护栏。最近做的一批缺陷清零里，就抓到并修掉了「平盘日被当成下跌」这类
        <b>不崩溃但结果错</b> 的静默缺陷 —— 一个 4.32% 样本量级的系统性偏置。</p>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>📊 项目规模（全部从仓库实时统计）</h2>
    <p class="lead">下面的数字由 <code>scripts/gen_portfolio_page.py</code> 从代码库直接算出，随代码更新自动刷新。</p>
    <div class="grid g4">
      <div class="stat"><div class="n">@PAGES@</div><div class="l">功能页面（Streamlit 多页）</div><div class="x">行情/事件/资金/情绪/策略/交易/AI</div></div>
      <div class="stat"><div class="n">@ROUTES@</div><div class="l">后端 REST 端点</div><div class="x">Flask + JWT 鉴权</div></div>
      <div class="stat"><div class="n">@SRC_LOC@</div><div class="l">行自研源码</div><div class="x">@PY_FILES@ 个 Python 文件</div></div>
      <div class="stat"><div class="n">@TESTS@</div><div class="l">自动化测试用例</div><div class="x">@TEST_FILES@ 个测试文件</div></div>
      <div class="stat"><div class="n">@BREADTH@</div><div class="l">真实交易日广度基座</div><div class="x">@BREADTH_SPAN@ · 全市场广度</div></div>
      <div class="stat"><div class="n">@STOCKS@</div><div class="l">覆盖标的</div><div class="x">逐股日线缓存重建</div></div>
      <div class="stat"><div class="n">@COMMITS@</div><div class="l">Git 提交</div><div class="x">@DAYS@ 个工作日 · @SPAN@</div></div>
      <div class="stat"><div class="n">4</div><div class="l">级数据源自动降级</div><div class="x">AKShare→BaoStock→新浪→东财→缓存</div></div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>📈 实证结果（真实图表，来自本地数据与运行产物）</h2>
    <p class="lead">这些图不是示意图：图 1 由自建广度基座（@BREADTH_SPAN@ 共 @BREADTH@ 个交易日）实算出图；
    图 2–4 由每日自动落盘、次日回填的评估闭环产出，样本仍在累积，故只呈现事实、不做过强断言。
    回测脚本与生产代码共用同一套 <code>locate_cycle</code> / <code>derive_position</code>，零前视。</p>
    <div class="grid g2">
      @CHARTS@
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>🖥 界面与产出实拍</h2>
    <p class="lead">截图与图表全部由 <code>scripts/gen_screenshots.py</code> / <code>thesis/gen_backtest_eval.py</code>
      从本地 SQLite 真实缓存与真实回测引擎导出 —— <b>没有一张是合成数据或示意曲线</b>。
      这一点我们专门做过一次自查：早期脚本里确实有两处用随机数兜底的图，已全部改为真实数据或直接跳过。</p>
    <div class="grid g3">
      @SHOTS@
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>🧪 工程素养：一轮「静默缺陷清零」实录</h2>
    <p class="lead">
      测试全绿 ≠ 代码正确。我专门做过一批针对「<b>不崩溃但语义错</b>」缺陷的审计迭代，每轮都要求：
      能指认证据 → 修复 → 加护栏 → 提交。下表是其中几例。
    </p>
    <table>
      <tr><th>缺陷</th><th>为什么危险</th><th>证据</th><th>修法</th></tr>
      <tr>
        <td>平盘日被判为「方向错误」</td>
        <td>偏空预测在平盘日白拿命中，命中率被系统性高估</td>
        <td class="mono">4093 日中 177 天平盘<br>49.3% → 49.1%</td>
        <td>三态口径（平盘=无信息）+ 历史记录幂等纠正</td>
      </tr>
      <tr>
        <td>缓存清除「双重静默失败」</td>
        <td>删除失败被吞，界面仍报「缓存已清除」→ 用户拿旧数据当新行情</td>
        <td class="mono">库被锁 → 0 提示</td>
        <td>返回真实删除行数 + 分级留痕 + 据实反馈</td>
      </tr>
      <tr>
        <td>SQLite 连接泄漏</td>
        <td>Streamlit 每次交互整页重跑，连接累积 → 句柄耗尽、DB 被占</td>
        <td class="mono">2 处 _get_conn() 无 close</td>
        <td><code>contextlib.closing</code> + 全仓 AST 守卫</td>
      </tr>
      <tr>
        <td>基准窗口外的预测被「造」出收益</td>
        <td>老记录被塞上 400 天后的涨跌幅冒充「次日涨跌」，静默污染校准</td>
        <td class="mono">base=sd[0] 兜底</td>
        <td>返回「无法判定」+ 单独计数并在面板披露</td>
      </tr>
    </table>
    <p class="note">每一轮都补了对应的回归测试与源码护栏（AST 断言），防止同一类问题回流。</p>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>🏗 系统架构</h2>
    <div class="arch">┌──────────────────────────────┐        ┌─────────────────────────────────────┐
│  Streamlit 多页前端 :8899     │  HTTP  │  Flask 后端 :5050                    │
│  @PAGES@ 个功能页面 + @MODULES@ 业务模块    │ ─────▶ │  @ROUTES@ 个 REST 端点 · JWT 鉴权 · 限流   │
│  双主题 · A股红涨绿跌         │  JWT   └──────────────┬──────────────────────┘
└───────────────┬──────────────┘                       │ SQLAlchemy
                │                                      ▼
                │                    ┌────────────────────────────────────┐
                │                    │  SQLite · 用户 / 配置 / 操作日志     │
                ▼                    └────────────────────────────────────┘
   数据源降级链（前端取数）
   AKShare ─▶ BaoStock ─▶ 新浪财经 ─▶ 东方财富 ─▶ 本地 SQLite 缓存
   （行情 / K线 / 指数 / 板块 / 宏观 / 商品 / 财务）

   决策闭环（项目核心）
   情绪六阶段定位 ─▶ 仓位推导 ─▶ 每日落盘预测 ─▶ 次日回填打分 ─▶ 分组刻度校准
   ↑                                                            │
   └──────────────── 单一真理源 modules/decision.py ◀───────────┘</div>
    <div class="stack">
      <span>Python 3.13</span><span>Streamlit</span><span>Flask</span><span>SQLAlchemy</span>
      <span>PyJWT</span><span>Pandas</span><span>Plotly</span><span>Backtrader</span>
      <span>AKShare</span><span>BaoStock</span><span>Tushare</span><span>SQLite</span>
      <span>Pytest</span><span>GitHub Actions CI</span><span>Docker Compose</span><span>jieba / SnowNLP</span>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>💬 面试可深挖的三个问题（我准备好了）</h2>
    <div class="q">
      <b>Q1「方向命中率只有 @ACC@%，这不是说明模型没用吗？」</b>
      <p>恰恰相反，这是设计的结果。日频方向在有效市场里近似随机游走，硬凑一个 60% 只会是过拟合。
      我把可预测性配置在<b>更稳健的维度</b>——仓位刻度：进攻期平均 57.8% vs 防守期 35.0%，价差 22.8pt。
      也就是说，系统不回答「明天涨还是跌」，而回答「当下这个市场状态，该用多大仓位」。</p>
    </div>
    <div class="q">
      <b>Q2「你的校准模块凭什么不会过拟合？」</b>
      <p>三道硬约束：校准只产出<b>建议</b>（<code>as_patch()</code> 只返回 dict，绝不自动改写规则）；
      调节量被 clamp 在 ±5；样本不足或调节量落在噪音阈值内时，模块会<b>明确输出「不动」</b>而不是硬给一个数。
      回测里四个战术分组的建议调节量全部 <code>actionable=False</code>，机制选择了沉默——这正是它该有的行为。</p>
    </div>
    <div class="q">
      <b>Q3「@TESTS@ 个测试，怎么保证不是走过场？」</b>
      <p>用「能不能抓真 bug」来验收。举上面那个例子：测试全绿的状态下，我通过审计发现
      「次日恰为平盘」被当成下跌，导致 84 次虚假命中——修完立刻把命中率从 49.3% 改到 49.1%，
      同步修正论文，并加了一条把「论文数字钉死在实算产物上」的一致性测试。
      验收标准是<b>可观测的真实收益</b>，不是覆盖率数字。</p>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>🚀 一条命令跑起来</h2>
    <div class="cmd">git clone https://github.com/hzzqq/StockSignal.git
cd StockSignal
# Windows：双击 启动StockSignal.bat（自动建环境→初始化数据库→起前后端→开浏览器）
# 或手动：
pip install -r requirements.txt -r backend/requirements.txt
python -m backend.scripts.init_db
python -m flask --app backend.app:app run --host 127.0.0.1 --port 5050   # 后端
streamlit run app.py --server.port 8899                                   # 前端 → http://localhost:8899</div>
    <p class="note">默认体验账号 <code>demo / Demo@123</code>。数据全部走免费源 + 本地缓存，无需任何付费 API Key。</p>
  </div>
</section>

<footer>
  <div class="wrap">
    StockSignal · 个人独立项目（@SPAN@，@COMMITS@ 次提交）<br>
    本页由 <code>scripts/gen_portfolio_page.py</code> 自动生成 · 仅用于学习与研究，不构成任何投资建议
  </div>
</footer>

</body>
</html>
"""


def render(stats: dict) -> str:
    charts = []
    for rel, title, desc in CHARTS:
        uri = _data_uri(rel)
        if not uri:
            continue
        charts.append(
            f'<figure><img src="{uri}" alt="{title}"><figcaption><b>{title}</b>{desc}</figcaption></figure>'
        )
    shots = []
    for rel, title, tag in SHOTS:
        uri = _data_uri(rel)
        if not uri:
            continue
        shots.append(
            f'<figure class="shot"><img src="{uri}" alt="{title}">'
            f'<figcaption><b>{title}</b><span>{tag}</span></figcaption></figure>'
        )

    html = HTML.replace("@CSS@", CSS)
    repl = {
        "@PAGES@": str(stats["pages"]),
        "@MODULES@": str(stats["modules"]),
        "@ROUTES@": str(stats["routes"]),
        "@SRC_LOC@": f"{stats['src_loc']:,}",
        "@TESTS@": f"{stats['tests']:,}",
        "@TEST_FILES@": str(stats["test_files"]),
        "@TEST_LOC@": f"{stats['test_loc']:,}",
        "@GUARDS@": str(stats["guards"]),
        "@PY_FILES@": str(stats["py_files"]),
        "@BREADTH@": f"{stats['breadth_days']:,}",
        "@BREADTH_SPAN@": stats["breadth_span"] or "全历史",
        "@BT_DAYS@": f"{stats['bt']['scored']:,}",
        "@STOCKS@": f"{stats['stocks']:,}",
        "@COMMITS@": str(stats["commits"]),
        "@DAYS@": str(stats["days"]),
        "@SPAN@": f"{stats['first_day']} – {stats['last_day']}",
        # 回测三件套同样取自钉死的产物 JSON，不再手写（防漂移）
        "@ACC@": f"{stats['bt']['acc']:g}" if stats["bt"]["acc"] else "—",
        "@HIT@": str(stats["bt"]["hit"]) if stats["bt"]["hit"] else "—",
        "@CALL@": str(stats["bt"]["call"]) if stats["bt"]["call"] else "—",
        "@CHARTS@": "\n      ".join(charts),
        "@SHOTS@": "\n      ".join(shots),
    }
    for k, v in repl.items():
        html = html.replace(k, v)

    # 安全二次替换：CHARTS/SHOTS 的标题或描述里可能含 @BREADTH@ / @BREADTH_SPAN@ 等占位符，
    # 这些键在主循环里先于 @CHARTS@ 被替换，而图注 HTML 是在 @CHARTS@ 注入时才进入 html 的，
    # 因此图注内的占位符不会被主循环替换 → 永久残留（守卫测试 test_render_* 曾抓到）。
    # 广度/回测键的值与位置无关、且本身不含占位符，可无条件二次替换兜底。
    for k in ("@BREADTH@", "@BREADTH_SPAN@", "@BT_DAYS@", "@ACC@", "@HIT@", "@CALL@"):
        html = html.replace(k, repl[k])
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 StockSignal 作品集主页（单文件 HTML）")
    ap.add_argument("--fast", action="store_true", help="跳过 pytest 收集（用 AST 计数，秒出）")
    ap.add_argument("--out", default=OUT, help=f"输出路径（默认 {os.path.relpath(OUT, ROOT)}）")
    args = ap.parse_args()

    fast = args.fast
    stats = collect(fast=fast)
    if not fast and not stats["tests_exact"]:
        print("[warn] pytest 收集失败，退回 AST 计数")
    html = render(stats)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(out) / 1024 / 1024
    print(f"[portfolio] 已生成 {os.path.relpath(out, ROOT)}  （{size:.2f} MB，单文件自包含）")
    print(f"[portfolio] 页面 {stats['pages']} · 端点 {stats['routes']} · 源码 {stats['src_loc']:,} 行 · "
          f"测试 {stats['tests']:,}{'' if stats['tests_exact'] else '(AST)'} · 护栏文件 {stats['guards']}")
    print(f"[portfolio] 广度 {stats['breadth_days']:,} 交易日 · 标的 {stats['stocks']:,} · "
          f"提交 {stats['commits']} · 跨度 {stats['first_day']}–{stats['last_day']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
