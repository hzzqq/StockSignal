"""
弹性自动刷新单点（streamlit_autorefresh 适配层）。

背景：多个页面/组件用 `streamlit_autorefresh.st_autorefresh` 实现定时自动刷新。
该第三方包并非所有运行环境都预装；一旦缺失，凡是顶层 `from streamlit_autorefresh
import st_autorefresh` 的页面会在加载时直接 ModuleNotFoundError 硬崩溃（见 pages/2_个股分析.py、
pages/2_多股对比.py、pages/C_自选股监控.py）。

这里统一收敛为单点导入：
- 包存在 → 透传真实 `st_autorefresh`（行为完全不变）；
- 包缺失 → 降级为 no-op，页面不再崩溃，只是失去自动刷新（可接受降级）。

所有引用方改为 `from modules.autorefresh import st_autorefresh` 即可。
同时建议在 requirements.txt 显式声明 `streamlit-autorefresh` 以恢复完整行为。
"""

from __future__ import annotations

try:
    from modules.autorefresh import st_autorefresh as _st_autorefresh  # type: ignore
except ImportError:  # pragma: no cover - 仅在未安装该包时触发
    def _st_autorefresh(*_args, **_kwargs):
        """缺失依赖时的零操作降级：接受任意参数，不抛异常。"""
        return None


# 对外统一导出，引用方 `from modules.autorefresh import st_autorefresh`
st_autorefresh = _st_autorefresh
