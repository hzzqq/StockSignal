"""
每日市场情绪缓存刷新入口（供 WorkBuddy automation 调用）。

必须放在独立模块并加 `if __name__ == "__main__"` 守卫：
refresh_all_indicators 内部用 ProcessPoolExecutor 子进程隔离 py_mini_racer(V8)
原生崩溃；Windows 下子进程会以 spawn 方式重新导入 __main__ 模块，若没有
守卫会递归重跑 refresh_all_indicators 造成进程炸弹。本守卫避免该问题。

调用方式（项目根目录，venv python）：
    PYTHONPATH=/e/project/ks/StockSignal \
    python -m modules._refresh_runner
"""
import json

from modules.market_cache import refresh_all_indicators


if __name__ == "__main__":
    r = refresh_all_indicators()
    print(json.dumps(r, ensure_ascii=False, indent=2))
