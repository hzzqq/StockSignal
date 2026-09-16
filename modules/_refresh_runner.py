"""
每日市场情绪缓存刷新入口（供 WorkBuddy automation 调用）。

必须放在独立模块并加 `if __name__ == "__main__"` 守卫：
refresh_all_indicators 内部用 ProcessPoolExecutor 子进程隔离 py_mini_racer(V8)
原生崩溃；Windows 下子进程会以 spawn 方式重新导入 __main__ 模块，若没有
守卫会递归重跑 refresh_all_indicators 造成进程炸弹。本守卫避免该问题。

调用方式（项目根目录，venv python）：
    python -m modules._refresh_runner            # 按 TTL 刷新
    python -m modules._refresh_runner --force    # 忽略 TTL，强制刷新

⚠️ 红线：禁止改写成 `python -c "from modules.market_cache import refresh_all_indicators; ..."`。
   `python -c` 的代码会成为 spawn 子进程的 __main__ 且没有守卫 → 递归进程炸弹。
   任何触发 ProcessPoolExecutor 的入口都必须经由本模块（或自带 __main__ 守卫的脚本）。
   守卫见 tests/test_refresh_main_guard.py。
"""
import json
import sys

from modules.market_cache import refresh_all_indicators


def main(argv=None) -> int:
    """入口函数（可测）：解析 --force 后调用刷新，返回退出码。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in argv
    r = refresh_all_indicators(force=force)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
