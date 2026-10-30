"""T-229 P1 页面精简守卫（AST 离线检查，无需起 Streamlit）。

钉住四页「次要模块收进折叠区 / 重复模块删除」的契约，防止后续改动把
主功能区重新撑爆或误删折叠结构：

- 91_我的：唯一设置入口（分区版），「设置一览」重复控件版不得回归；
  「账号绑定 / 系统通知」占位不得回归；我的收藏/快速查看收进「更多功能」折叠区；
- 30_策略回测：回撤带（与回撤曲线同源重复）不得回归；五个次要工具在
  「更多回测工具」折叠区内调用；
- 35_资金流向：三个走势对比 fragment 在「走势扩展对比」折叠区内调用，
  红涨绿跌语义（红=净流入）保留在页头 caption；
- 16_财报日历：个股财报查询在折叠区内调用（财务三表能力保留）。
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _src(page: str) -> str:
    return (REPO / "pages" / page).read_text(encoding="utf-8")


def _tree(page: str) -> ast.AST:
    return ast.parse(_src(page), filename=page)


def _host_fn_src(module: str, fnname: str) -> str:
    """P0-1c 定位修正：40/41 页实现体=modules/portfolio_views.py 对应渲染函数。

    函数体级扫描（防同模块跨子页内容互相污染，如 46 页的「回到顶部」会误伤
    test_40 的重复回顶断言）；断言本体不变，同 P0-1b test_11 先例。
    """
    _sr = (REPO / "modules" / module).read_text(encoding="utf-8")
    _ast = ast.parse(_sr)
    _fn = next(n for n in _ast.body if isinstance(n, ast.FunctionDef) and n.name == fnname)
    return "\n".join(_sr.splitlines()[_fn.lineno - 1:_fn.end_lineno])


def _expander_label(call: ast.Call) -> str | None:
    """安全提取 st.expander 第一个位置参数的静态文本（f-string 返回拼接的常量部分）。"""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant):
        return str(arg.value)
    if isinstance(arg, ast.JoinedStr):  # f-string：取其中的常量片段拼接
        return "".join(str(v.value) for v in arg.values if isinstance(v, ast.Constant))
    return None


def _top_level_expanders(page: str) -> list[str]:
    """收集模块顶层（缩进级）with st.expander 的标签。"""
    labels = []
    for node in ast.walk(_tree(page)):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    label = _expander_label(call)
                    if label is not None:
                        labels.append(label)
    return labels


# ───────────────────────── 91_我的 ─────────────────────────
def test_91_no_duplicate_settings_panel():
    src = _src("91_我的.py")
    assert "当前全部设置一览" not in src, "重复的设置一览控件版不得回归（与分区版写同一状态）"


def test_91_placeholders_removed():
    src = _src("91_我的.py")
    assert "账号绑定" not in src, "占位按钮（仅提示暂未启用）不得回归"
    assert "系统通知" not in src, "纯占位空态不得回归"
    assert "我的导读" not in src


def test_91_secondary_in_expander():
    labels = "\n".join(_top_level_expanders("91_我的.py"))
    assert "更多功能（我的收藏 · 快速查看股票）" in labels
    src = _src("91_我的.py")
    assert src.count("查看示例自选股") == 0, "编造示例数据面板不得回归（诚实语义）"


# ───────────────────────── 30_策略回测 ─────────────────────────
def test_30_no_duplicate_drawdown_band():
    src = _src("30_策略回测.py")
    assert "回撤带" not in src, "回撤带与回撤曲线同源重复，不得回归"
    assert "downsample" not in src


def test_30_secondary_fragments_wrapped():
    """五个次要回测工具的**调用**必须位于「更多回测工具」折叠区内部。"""
    tree = _tree("30_策略回测.py")
    wrapped: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    if call.args and "更多回测工具" in (_expander_label(call) or ""):
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                                fn = sub.value.func
                                if isinstance(fn, ast.Name):
                                    wrapped.add(fn.id)
    for fn in ("fragment_strong_bull", "fragment_param_scan",
               "fragment_batch_backtest", "fragment_walk_forward", "fragment_run_history"):
        assert fn in wrapped, f"{fn} 必须在「更多回测工具」折叠区内调用"


# ───────────────────────── 35_资金流向 ─────────────────────────
def test_35_trend_fragments_wrapped_and_semantics_kept():
    tree = _tree("35_资金流向.py")
    wrapped: set[str] = set()
    label_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    if call.args and "走势扩展对比" in (_expander_label(call) or ""):
                        label_found = True
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                                fn = sub.value.func
                                if isinstance(fn, ast.Name):
                                    wrapped.add(fn.id)
    assert label_found, "「走势扩展对比」折叠区不得移除"
    for fn in ("fragment_index_trend", "fragment_industry_trend", "fragment_etf_trend"):
        assert fn in wrapped, f"{fn} 必须在折叠区内调用"
    src = _src("35_资金流向.py")
    assert "红=净流入、绿=净流出" in src, "A股红涨绿跌全局语义不得丢失"


# ───────────────────────── 16_财报日历 ─────────────────────────
def test_16_stock_financials_wrapped():
    tree = _tree("16_财报日历.py")
    wrapped = False
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    if call.args and "个股财报查询" in (_expander_label(call) or ""):
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                                if getattr(sub.value.func, "id", "") == "fragment_stock_financials":
                                    wrapped = True
    assert wrapped, "个股财报查询必须在折叠区内调用（财务三表能力保留）"


# ═══════════════════════ T-230 P2 批次 ═══════════════════════
def test_42_removed_decorations():
    """模拟交易：随机推荐 / 空快捷键占位 / 重复导读卡 不得回归。"""
    src = _src("42_模拟交易.py")
    assert "相关标的推荐" not in src, "随机 5 只推荐（每次刷新都变）不得回归"
    assert "⌨️ 快捷键" not in src, "自述无快捷键的空占位不得回归"
    assert 'sf_card("🎮 模拟交易组合"' not in src
    assert 'import random' not in src
    assert "使用说明" in src and "我的收藏" in src


def test_51_removed_hardcoded_and_wrapped():
    """每日晨报：硬编码推荐/回顶删除，事件榜在折叠区内调用。"""
    src = _src("51_每日晨报.py")
    assert "相关标的推荐" not in src, "硬编码 5 只示例股推荐不得回归"
    assert "morning_back_to_top" not in src, "与全局悬浮重复的回顶按钮不得回归"
    assert "免责与导读" not in src
    wrapped = False
    for node in ast.walk(_tree("51_每日晨报.py")):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    if call.args and "事件驱动看多榜" in (_expander_label(call) or ""):
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                                if getattr(sub.value.func, "id", "") == "fragment_event_driven_pool":
                                    wrapped = True
    assert wrapped, "事件驱动看多榜必须在折叠区内调用"


def test_40_removed_and_wrapped():
    """仓位管理：导读卡/重复回顶删除，辅助操作折叠，归因与卖出逻辑保留。"""
    # P0-1c 定位修正：40 页实现体=render_position_manager（断言本体不变）
    src = _host_fn_src("portfolio_views.py", "render_position_manager")
    assert "仓位管理导读" not in src
    assert "回到顶部" not in src, "与全局悬浮重复的回顶按钮不得回归"
    assert "scroll_nav" not in src, "回顶删除后不应残留 scroll_nav 死 import"
    assert 'st.expander("⚙️ 更多操作（加入自选 · 本地收藏 · 最近浏览）"' in src
    assert "pnl_attribution" in src and "pm_add_watch" in src and "pm_fav_add" in src


def test_14_removed_and_wrapped():
    """智能盯盘：导读卡/公式教学删除，跨页导航折叠，溯源徽标与来源披露保留。"""
    src = _src("14_智能盯盘.py")
    assert "智能盯盘 · 实时聚合" not in src
    assert "涨跌% = (现价-昨收)" not in src, "基础公式教学不得回归"
    assert 'st.expander("🔗 相关页面", expanded=False)' in src
    assert "prov_badge(build_display_provenance" in src, "展示源溯源徽标调用（T-218）不得移除"
    assert "非交易所逐笔主力数据" in src, "估算口径诚实说明不得丢失"


def test_11_removed_and_merged():
    """股票选取：导读卡删除，图表/指标教学合并进折叠区。"""
    # P0-1b 定位修正：11 页实现体=modules/stock_research.py::render_stock_picker
    # 函数体（只扫 picker 部分，不混入同模块 analysis 部分；断言本体不变，spec §1.6 预授权）
    _sr = (REPO / "modules" / "stock_research.py").read_text(encoding="utf-8")
    _tree = ast.parse(_sr)
    _fn = next(n for n in _tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_stock_picker")
    src = "\n".join(_sr.splitlines()[_fn.lineno - 1:_fn.end_lineno])
    assert "股票选取导读" not in src
    assert 'st.expander("📘 图表与指标说明", expanded=False)' in src
    assert "双击K线柱" not in src, "K线教学 caption 应已合并进折叠区"


def test_25_debug_params_wrapped_and_log_collapsed():
    """QuantAgent：日志流默认收起，调试参数在「高级选项」折叠区内。"""
    src = _src("25_QuantAgent投研.py")
    assert 'st.expander("🪵 实时协作日志", expanded=False)' in src, "实时日志应默认收起"
    assert "数据底座复用 StockSignal" not in src
    assert 'st.expander("⚙️ 高级选项' in src
    for k in ("use_browser", "use_rag", "force_human", "engine"):
        assert k in src, f"{k} 参数不得丢失"


def test_94_removed_and_wrapped():
    """消息中心：导读卡删除，低频操作/收藏折叠，已读逻辑与来源标注保留。"""
    src = _src("94_消息中心.py")
    assert 'sf_card("🔔 消息 / 通知中心"' not in src
    assert 'st.expander("⚙️ 更多操作（清除已读标记 · 重新加载）"' in src
    assert 'st.expander(f"⭐ 我的收藏（{len(_msg_starred_ids)}）"' in src
    assert "msg_read_ids" in src and "mark_all" in src
    assert "数据来源：自选股实时行情" in src


# ═══════════════════════ T-231 P3 批次 ═══════════════════════
def test_41_pnl_snapshot_wrapped():
    """组合收益：导读卡删除，盈亏快照（与仓位管理同源）在折叠区内。"""
    # P0-1c 定位修正：41 页实现体=render_portfolio_returns（断言本体不变）
    src = _host_fn_src("portfolio_views.py", "render_portfolio_returns")
    assert 'sf_card("📊 自选股组合收益跟踪"' not in src
    assert 'st.expander("💰 当前盈亏快照（与仓位管理页同源）"' in src
    assert "_show_attribution()" in src, "个股收益贡献保留主区"
    assert "pnl_attribution" in src


def test_10_removed_duplicates():
    """行情看板：导读卡/重复解释/搜索说明 caption 删除，溯源徽标与教学折叠保留。"""
    src = _src("10_行情看板.py")
    assert "页面导读" not in src
    assert "💡 解释：数值越接近 1" not in src, "与「怎么看这张图」expander 同义的 caption 不得回归"
    assert "输入代码 / 名称 / 拼音首字母，匹配结果" not in src
    assert 'st.expander(\'📖 怎么看这张图？\'' in src, "相关性教学折叠区保留"
    assert "prov_badge" in src, "展示源溯源徽标（T-215）不得移除"
    assert "wb_add_wl" in src, "加入自选交互保留"


def test_93_sysinfo_wrapped():
    """系统配置：静态系统信息卡在折叠区内，数据源健康度保留主区（不得被包进 expander）。"""
    src = _src("93_系统配置.py")
    assert 'st.expander("🖥️ 系统信息（服务地址 · 存储路径）"' in src
    assert "Flask API: `http://127.0.0.1:5050`" in src, "系统信息内容保留（仅折叠）"
    tree = _tree("93_系统配置.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            # sf_card / xc_content_card 为 from modules.* import 的裸 Name 调用
                            fname = getattr(sub.func, "id", "") or getattr(sub.func, "attr", "")
                            if fname in ("sf_card", "xc_content_card") and any(
                                a and isinstance(a, ast.Constant) and "健康度" in str(a.value)
                                for a in sub.args
                            ):
                                raise AssertionError("数据源健康度 sf_card/xc_content_card 不得被包进 expander（须保留主区）")


def test_92_intro_card_removed():
    """用户管理：导读卡删除，三 Tab 结构保留。"""
    src = _src("92_用户管理.py")
    assert "管理员视图" not in src
    assert "tab_users" in src and "tab_create" in src and "tab_logs" in src


# ═══════════════════════ 重复页头卡守卫（本次修复） ═══════════════════════
# 系统性缺陷：render_standard_page 已渲染页头（标题 + 简介 caption），其下方又紧跟
# 一张 sf_card，标题/正文与页头高度重复 → 视觉上「两个组件内容一样」。
# 已删除下列页面顶部多余的 sf_card，此处锁死不得回归。
_HEADER_DUP_CARDS = {
    "52_股吧.py": 'sf_card("💬 股吧 · 社区讨论"',
    "33_ETF筛选.py": 'sf_card("🧰 ETF / 基金筛选器"',
    "34_体检扫描.py": 'sf_card("🩺 一键体检扫描台"',
    "44_智能条件单.py": 'sf_card("🤖 智能条件单"',
    "43_实盘交易.py": 'sf_card("💰 实盘交易 · 下单入口"',
    "32_智能选股.py": 'sf_card("智能选股导读"',
    "31_形态选股.py": 'sf_card("技术形态选股器导读"',
    "15_市场驱动力.py": 'sf_card("五维驱动力导读"',
    "50_市场情绪.py": 'sf_card("市场温度计导读"',
    "23_事件追踪.py": 'sf_card("事件追踪导读"',
    "12_板块轮动.py": 'sf_card("板块轮动导读"',
    "22_基本面分析.py": 'sf_card("基本面分析导读"',
}


def test_no_duplicate_header_cards():
    """页头（render_standard_page）之外不得再出现与其同题/同义的 sf_card 重复卡。"""
    for page, forbidden in _HEADER_DUP_CARDS.items():
        src = _src(page)
        assert forbidden not in src, f"{page} 顶部重复页头卡不得回归：{forbidden}"

