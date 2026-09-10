"""tests/test_screenshot_no_fabrication.py

截图/图表**不得使用合成数据**守卫（2026-09-10）。

背景：一次面向求职展示的自查里发现，``scripts/gen_screenshots.py`` 里有两处
「不报错但语义全错」的产物，而这两张图正被 README 与推广物料公开引用：

1. ``shot_backtest_curve()`` 用 ``np.random`` 编了一条"策略跑赢基准、年化约 12%"
   的净值曲线，只因列名与 ``Visualizer.backtest_curve`` 契约不匹配而**静默退化成
   一张报错占位图**（"回测数据缺失：需要 date / cumulative_return 列"）。
   换句话说：磁盘上躺着一张伪造的业绩图，且线上 README 展示的是一张报错图。
   对一个以「诚实负结果、不编数字」为卖点的项目，这是致命风险 —— 只要有人把列名
   对齐，假曲线就会以真截图的样子流出去。

2. ``shot_signal_radar()`` 传的是 ``{"趋势","动量","量能","形态"}``，而
   ``Visualizer.signal_radar`` 只读 ``price_score / event_score / macro_score``，
   三键全 miss → 取值 0 → 导出一张**塌缩在原点的空雷达图**，标题却写着
   "600519 技术面四维评分雷达图"。异常分支还会用硬编码分数（72/58/65/48）兜底。

本测试把三条不变量锁死：
  A. 截图脚本不得含任何随机数造数代码；
  B. 传给 visualizer 的 dict 键必须**覆盖** visualizer 实际读取的键（契约守卫，
     即上面第 2 类 bug 的直接克星）；
  C. 公开文档里引用的图片必须真实存在，且引用的测试/页面规模数字必须与实际一致。
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GEN_SHOTS = os.path.join(ROOT, "scripts", "gen_screenshots.py")
GEN_PORTFOLIO = os.path.join(ROOT, "scripts", "gen_portfolio_page.py")
GEN_BACKTEST_FIG = os.path.join(ROOT, "thesis", "gen_backtest_eval.py")
VISUALIZER = os.path.join(ROOT, "modules", "visualizer.py")
PUBLIC_DOCS = ["README.md", "docs/promo-final.md", "docs/promo-template.md"]


def _src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _tree(path):
    return ast.parse(_src(path))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"未找到函数 {name}")


# ── A. 截图脚本不得造数 ──────────────────────────────────────────────

def test_gen_screenshots_contains_no_random_data_generation():
    """截图脚本里不得出现任何随机数造数（历史缺陷：np.random 伪造业绩曲线）。"""
    src = _src(GEN_SHOTS)
    for banned in ("np.random", "default_rng", "random.normal", "random.random",
                   "np.random.rand", "randn"):
        assert banned not in src, (
            f"gen_screenshots.py 出现造数代码 {banned!r}——截图必须来自真实缓存或真实引擎，"
            f"不得合成数据（历史缺陷见本文件 docstring）"
        )


def test_gen_screenshots_does_not_import_numpy():
    """造数能力整体移除后，numpy 导入也应一并清掉，避免后人顺手再写随机曲线。"""
    names = {a.name for n in _tree(GEN_SHOTS).body
             if isinstance(n, ast.Import) for a in n.names}
    assert "numpy" not in names, "gen_screenshots.py 不应再依赖 numpy"


def test_backtest_shot_uses_real_engine_not_synthetic_frame():
    """回测图必须调用真实 Backtester（含成本 A/B 两组），不得自造 DataFrame。"""
    fn = _func(_tree(GEN_SHOTS), "shot_backtest_curve")
    mods = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    assert "modules.backtest" in mods, "shot_backtest_curve 必须用真实回测引擎"
    body_src = ast.unparse(fn)
    assert "Backtester" in body_src
    # 含成本 / 零成本两组对照
    assert "slippage_pct" in body_src and "stamp_tax_pct" in body_src, \
        "回测图应含「含成本 vs 零成本」两组对照"


def test_backtest_shot_converts_timestamps_to_str():
    """x 轴必须转成日期字符串：传 Timestamp 会让 kaleido 序列化抛异常。"""
    # ast.unparse 会把引号统一成单引号，断言前先归一，避免断言变成引号风格测试
    src = ast.unparse(_func(_tree(GEN_SHOTS), "shot_backtest_curve")).replace('"', "'")
    assert "str(d)[:10] for d in with_cost.df['date']" in src, \
        "日期需转 str，否则 kaleido 报 'Type is not JSON serializable: Timestamp'"


# ── B. visualizer 契约守卫 ──────────────────────────────────────────

def _keys_read_by(func_name, dict_param):
    """从 visualizer 函数体里抽出 ``<dict_param>.get("key", ...)`` 读取的键。"""
    fn = _func(_tree(VISUALIZER), func_name)
    keys = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == dict_param
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            keys.add(node.args[0].value)
    return keys


def _keys_provided_by(func_name, dict_var):
    """从截图脚本的函数体里抽出 ``<dict_var> = {...}`` 的键集合。"""
    fn = _func(_tree(GEN_SHOTS), func_name)
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == dict_var
                and isinstance(node.value, ast.Dict)):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError(f"{func_name} 里未找到 {dict_var} = {{...}} 字面量")


def test_radar_shot_dict_keys_cover_visualizer_contract():
    """核心契约守卫：传给 signal_radar 的键必须覆盖 visualizer 实际读取的键。

    历史缺陷：截图脚本传 趋势/动量/量能/形态，visualizer 读 price_score/event_score/
    macro_score，三键全 miss → 全 0 → 塌缩空图（且不报错）。
    """
    required = _keys_read_by("signal_radar", "scores")
    assert required, "未能从 Visualizer.signal_radar 抽出契约键，守卫失效"
    provided = _keys_provided_by("shot_signal_radar", "scores")
    missing = required - provided
    assert not missing, (
        f"shot_signal_radar 缺少 signal_radar 必需的键 {sorted(missing)}；"
        f"缺失的键会被 .get(...,0) 取成 0，导出一张塌缩空图且无任何报错"
    )


def test_radar_shot_guards_against_all_zero_scores():
    """全 0 即视为契约不匹配，必须跳过而非导出误导性空图。"""
    src = ast.unparse(_func(_tree(GEN_SHOTS), "shot_signal_radar"))
    assert "not any(scores.values())" in src, "缺少全 0 契约守卫"
    assert "跳过" in src
    assert "72" not in src, "不应再出现硬编码示意分数"


# ── C. 公开文档 ↔ 磁盘事实 ──────────────────────────────────────────

def test_public_docs_referenced_screenshots_exist():
    """README / 推广物料里引用的 screenshots/*.png 必须真实存在（防挂死链）。"""
    ref_re = re.compile(r"(?:screenshots/[0-9A-Za-z_.\-]+\.png)")
    missing = []
    for rel in PUBLIC_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        for ref in set(ref_re.findall(_src(path))):
            if not os.path.exists(os.path.join(ROOT, ref)):
                missing.append(f"{rel} -> {ref}")
    assert not missing, "公开文档引用了不存在的截图（会显示为挂掉的外链）：" + "; ".join(missing)


def test_public_docs_test_count_is_single_consistent_value():
    """同一套规模数字在多处出现，任何一处漏改都算不一致（曾出现 1767 vs 2608）。"""
    pats = [
        r"(\d+)\s*(?:个)?(?:自动化)?(?:测试|用例)(?!文件)",
        r"测试\s+(\d+)\s*passed",
        r"Tests-(\d+)%20passed",
    ]
    seen = {}
    for rel in PUBLIC_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        text = _src(path)
        for pat in pats:
            for m in re.findall(pat, text):
                seen.setdefault(int(m), []).append(rel)
    assert seen, "未从公开文档中解析到任何测试规模数字，守卫失效"
    assert len(seen) == 1, (
        f"公开文档里的测试规模数字不一致：{ {k: sorted(set(v)) for k, v in seen.items()} }"
    )


def test_readme_page_count_matches_actual_pages():
    """README 声称的页面数必须等于 pages/ 下真实页面数。"""
    text = _src(os.path.join(ROOT, "README.md"))
    m = re.search(r"\*\*(\d+) 个功能页面\*\*", text)
    assert m, "README 未声明功能页面数"
    stated = int(m.group(1))
    actual = len([p for p in os.listdir(os.path.join(ROOT, "pages"))
                  if p.endswith(".py") and not p.startswith("_")])
    assert stated == actual, f"README 声称 {stated} 个页面，实际 {actual} 个"


def test_thesis_backtest_figure_prevents_title_clipping():
    """论文回测图须显式给足画布宽高，否则长中文标题被右边缘裁掉。"""
    src = _src(GEN_BACKTEST_FIG)
    assert "width=1200" in src and "height=640" in src, \
        "须显式设置画布宽高（默认 700x500 会把标题截断成 '…2026-09-0'）"
    assert "title=dict(" in src and 'xanchor="center"' in src, "标题应居中而非左贴边"


def test_portfolio_shot_captions_have_no_stale_misleading_titles():
    """作品集卡片标题必须描述真实图表（曾写 '收益曲线 vs 沪深300' 但图是成本 A/B）。"""
    tree = _tree(GEN_PORTFOLIO)
    shots = None
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == "SHOTS"):
            shots = ast.literal_eval(node.value)
    assert shots, "未找到 SHOTS 清单"
    titles = [s[1] for s in shots]
    for bad in ("沪深300", "回测数据缺失"):
        assert not any(bad in t for t in titles), f"卡片标题仍含误导内容 {bad!r}"
    for path, title, _tag in shots:
        assert os.path.exists(os.path.join(ROOT, path)), f"卡片引用不存在的图：{path}"
