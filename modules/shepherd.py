"""modules/shepherd.py —— 牧羊人广度信号，**单一真理源**。

R-05 拆分（2026-11-01）：本文件已变为 re-export 层，实际实现分散在：
  · shepherd_helper.py      —— 共享常量 + 顶层 helper（THRESHOLDS, _CACHE, _cached, logger, ...）
  · shepherd_fetch.py       —— 各数据源抓取 + get_shepherd_today
  · shepherd_history.py     —— 历史读/存/范围查询
  · shepherd_temperature.py —— 温度计算 + 晋级率 + 行业分布

对外 API 零变化：所有 public/private 符号仍在此模块命名空间。
monkeypatch 目标（如 "modules.shepherd._fetch_legu"）仍有效。
"""

from __future__ import annotations  # noqa: I001

from .shepherd_helper import *       # noqa: F401,F403
from .shepherd_fetch import *        # noqa: F401,F403
from .shepherd_history import *      # noqa: F401,F403
from .shepherd_temperature import *  # noqa: F401,F403
