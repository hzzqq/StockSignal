"""
股票选取模块
------------
位于「行情看板」与「个股分析」之间。
- 从行情看板迁入：参数设置、K 线图、技术面分析。
- 新增：加入自选股 / 加入垃圾股、用户打分、自选股/垃圾股折叠展示（可排序、可跳转）。
"""

from modules.stock_research import render_stock_picker

render_stock_picker()
