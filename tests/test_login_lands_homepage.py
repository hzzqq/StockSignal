"""T-367 登录落地守卫：登录成功后首屏应为首页 app.py（非行情看板）。

用户明确：登录进去第一眼看到的是首页。故 90_登录.py 登录成功的 safe_switch_page
目标必须是根入口 app.py，且已登录态的便捷入口也指向首页。
"""
import pathlib

PAGE = pathlib.Path(__file__).resolve().parents[1] / "pages" / "90_登录.py"
SRC = PAGE.read_text(encoding="utf-8")


def test_login_success_lands_on_homepage():
    # 登录成功跳转目标为根入口首页
    assert 'safe_switch_page("app.py")' in SRC
    # 不再跳转行情看板
    assert 'safe_switch_page("pages/10_行情看板.py")' not in SRC


def test_logged_in_shortcut_points_home():
    # 已登录用户访问 /登录 的便捷入口也指向首页
    assert "进入首页" in SRC
