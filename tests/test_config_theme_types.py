"""
tests/test_config_theme_types.py — .streamlit/config.toml 主题字段类型守卫（离线）

缺陷背景（T-312 E2E 勘测发现，源自 T-261）：baseFontSize 写成字符串 "17px"，
Streamlit 的 _populate_theme_msg 对 CustomTheme proto 的 base_font_size（int 字段）
setattr 时抛 TypeError: 'str' object cannot be interpreted as an integer。

危害链：该异常发生在每次 run 的 SCRIPT_STARTED 事件处理里 → NewSession 消息
（携带 fragment_ids_this_run）永远发不到前端 → 前端 run_every 轮询片段（星辰AI
_poll_ai_task 等）id 失联、tick 被服务端以「fragment does not exist anymore」拒绝
→ 任务终态永不自动取回（T-309 轮询架构被静默绞杀）。

钉住契约：theme.baseFontSize 必须是 int（Streamlit 官方模板均为 baseFontSize = 14 整型）。
mutation 目标：改回 "17px" 字符串 → 本测试变红。
"""
import tomllib
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"


def _load_theme() -> dict:
    with open(CONFIG, "rb") as f:
        data = tomllib.load(f)
    return data.get("theme") or {}


def test_base_font_size_is_int():
    """baseFontSize 必须是整型像素值——字符串会让 NewSession 消息创建抛 TypeError，
    全站 run_every 轮询片段失联（T-309 架构被静默绞杀）。"""
    theme = _load_theme()
    assert "baseFontSize" in theme, "config.toml [theme] 缺少 baseFontSize（T-261 字号意图丢失）"
    val = theme["baseFontSize"]
    assert isinstance(val, int) and not isinstance(val, bool), (
        f"baseFontSize 必须是整型像素值（如 17），当前为 {val!r}（{type(val).__name__}）——"
        "字符串值会让 Streamlit _populate_theme_msg 抛 TypeError，"
        "NewSession 消息（携带 fragment ids）发不到前端，run_every 轮询片段全站失联"
    )
    assert 12 <= val <= 24, f"baseFontSize={val} 超出合理像素范围 [12, 24]"


def test_theme_color_fields_are_strings():
    """主题色字段必须是字符串（hex），防止同类类型错配以其他字段复发。"""
    theme = _load_theme()
    for key in ("primaryColor", "backgroundColor", "secondaryBackgroundColor", "textColor"):
        if key in theme:
            val = theme[key]
            assert isinstance(val, str), (
                f"theme.{key} 必须是字符串（hex 色值），当前为 {val!r}（{type(val).__name__}）"
            )
