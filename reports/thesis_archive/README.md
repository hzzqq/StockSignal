# 论文章节归档（被主稿取代，保留备查）

本目录下的文件是 R30–R32 期间产出的「7 章并行稿」与各章独立稿，**已被
`thesis/StockSignal_毕业论文_完整稿.md`（77KB，8 章完整稿）取代**。

## 为什么归档而非删除
- 主稿（77KB）结构更完整（含 Ch5 创新点代码附录 A.1–A.7、Ch6 系统测试与评估），
  且已在第 6 章注入 R30–R31 的 **4092 天大规模历史回测实证**（方向 49.3%≈随机、
  仓位随周期分化 22.8pt，图 6-6/6-7）。继续在 `reports/` 根目录保留并行稿会造成重复与混淆。
- 但 `thesis_ch03_data_foundation.md`（R30）是**独立的「数据基础与实证分析」专章**，
  主稿 Ch3 为「系统需求分析与总体设计」、未单列数据基础章，故该文件仍有独立参考价值，故保留归档而非删除。

## 各文件用途
| 文件 | 原用途 |
|---|---|
| thesis_abstract.md | 摘要（含 49.3% / 22.8pt 真实数字） |
| thesis_ch01_introduction.md | 第 1 章 绪论 |
| thesis_ch02_related_work.md | 第 2 章 相关技术 |
| thesis_ch03_data_foundation.md | 第 3 章 数据基础与实证（**独立价值最高**） |
| thesis_ch04_decision_closure_backtest.md | 第 4 章 决策闭环回测实证 |
| thesis_ch05_scale_calibration.md | 第 5 章 刻度校准实证 |
| thesis_ch06_system_design.md | 第 6 章 系统总体设计 |
| thesis_ch07_conclusion.md | 第 7 章 结论与展望 |
| thesis_references.md | 参考文献（GB/T 7714 ×20） |
| thesis_full_draft.md | 7 章整合稿（683 行） |

## 权威主稿
- `thesis/StockSignal_毕业论文_完整稿.md` —— 论文唯一权威完整稿。
- 所有实证数字以 `reports/backtest_decision_closure.json` 与 `data/shepherd_history.csv` 为准。
- 2007–2014 历史广度补全见 `scripts/reconstruct_breadth_baostock.py`（BaoStock 路径，已冒烟验证）。
