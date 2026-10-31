"""T-367 登录页行情台守卫：登录前可见今日市场实时变化，且诚实不编造。

- 左栏行情台：资金温度 / 今日市场 / AI 信号 三块均存在；
- 真实上证指数走内联短超时抓取、失败降级（_fetch_sh_index 返回 None 而非抛错/编造）；
- 登录方式 Tab 为 密码登录 / 验证码登录 / 注册；验证码登录在离线环境诚实标注未接入短信网关。
"""
import pathlib

PAGE = pathlib.Path(__file__).resolve().parents[1] / "pages" / "90_登录.py"
SRC = PAGE.read_text(encoding="utf-8")


def test_market_desk_present():
    # 行情台三大块均存在
    assert "资金温度" in SRC
    assert "今日市场" in SRC
    assert "AI 信号" in SRC
    # 数据来源：本地快照 + 真实指数抓取函数
    assert "_login_market_pulse" in SRC
    assert "_fetch_sh_index" in SRC


def test_index_fetch_degrades_gracefully():
    # 抓取失败必须返回 None（绝不编造/抛未捕获异常导致登录页崩）
    assert "except Exception" in SRC
    assert "return None" in SRC
    # 且使用短超时，避免登录页卡死
    assert "timeout=2.5" in SRC


def test_login_tabs_and_honest_sms():
    # 登录方式标签：密码登录 / 验证码登录 / 注册
    assert "密码登录" in SRC
    assert "验证码登录" in SRC
    assert "注册" in SRC
    # 验证码登录诚实标注：离线未接入短信网关（不做假功能）
    assert "未接入短信网关" in SRC
    assert "按钮已禁用" in SRC


def test_no_obsolete_account_login_tab():
    # 旧「账号登录」独立标签已被「密码登录」取代
    assert 'st.tabs(["🔑 账号登录"' not in SRC
