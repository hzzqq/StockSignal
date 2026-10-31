"""
消息 / 通知中心（聚合页）
----------------------------
把分散在各模块的「提醒」汇成一条统一信息流：

  🔔 异动  —— 自选股当日涨跌异动（基于实时行情计算）
  💬 社区  —— 股吧最新帖子 / 评论动态
  🛡️ 系统  —— 数据源健康度、使用提示
  🔬 研究  —— 研究智能体定时自驱盯盘产出（H1+ 方向 B，含引用溯源）

每个区块独立取数（safe_section 隔离），单源失败不影响其它模块。
支持按类型筛选、标记已读、点击跳转到对应模块。
"""
import logging

import streamlit as st
from datetime import datetime
import math
import concurrent.futures as _cf

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_metric
from modules.session import safe_switch_page, api_get, trading_autorefresh
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, render_data_degradation_banner
from modules.page_utils import fmt_rel as _fmt_rel

logger = logging.getLogger(__name__)
from modules.page_widgets import UP, DOWN
from modules.format_helpers import extract_pct

from modules.ui_kit import xc_success_box, xc_warn_box, info_banner
dark = render_standard_page(
    title="消息 / 通知中心", icon="🔔",
    caption="聚合自选股异动、社区动态与系统状态；各模块独立取数，互不干扰。",
)
trading_autorefresh(key="message_autorefresh")

FETCHER = StockFetcher()


def _pct(q):
    try:
        if not q or not q.get("prev_close"):
            return 0.0
        cur = q.get("current")
        prev = q.get("prev_close")
        if cur is None or prev in (None, 0):
            return 0.0
        return (float(cur) - float(prev)) / float(prev) * 100
    except Exception:
        return 0.0


def _color(pct):
    return UP if pct >= 0 else DOWN


def _safe_title_html(title, read=False):
    """转义消息标题中的 HTML，防止存储型 XSS；已读消息加删除线。

    纯函数：仅依赖标准库 html.escape，不访问 st / 网络 / 会话状态。
    """
    import html
    t = html.escape(str(title or ""))
    return f"~~{t}~~" if read else t
