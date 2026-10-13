# 研究智能体量化评测（T-273B）

> 毕设补充章节素材。数字全部来自 `reports/research_agent_eval.json`
> （套件 `scripts/agent_eval_suite.py`，与守卫 `tests/test_research_agent_eval.py`
> 同源，可一键复现）。工具层全 mock 零网络；**不评测 LLM 措辞质量**（规则合成器
> 路径），LLM 路径不在离线评测范围——此边界如实标注。

## 1. 评测设计

对标 Agent 评测方法论（AgentBench 式「能力维度 × 任务实例」），对星辰 AI 的
研究智能体（`research_agent.run_research`：规划 → 有界执行 → 带引用综合）做
**五维 × 9 题**行为契约评测：

| 维度 | 题 | 考什么 |
|---|---|---|
| 任务完成/调用序列 | E1, E2 | 默认规划器端到端三件套；注入多步计划的执行顺序保真 |
| 引用溯源 | E3 | citations 回填 as_of；answer 带 [S#] 标记与「数据截至」 |
| 诚实降级 | E4, E5 | 全失败 → unavailable 且**零编造**；部分失败 → partial 且 citations 只含成功步 |
| 只读红线 | E6 | 恶意计划里的 conditional_orders 写操作被拒且**工具零调用** |
| 有界执行 | E7, E8, E9 | 步数截断留痕；max_steps clamp 上限 8；时间预算中断 partial |

评测的意义在于**用对抗性任务暴露实现缺陷**，而非证明系统正确。

## 2. 结果：9/9 通过，但首轮抓到 1 个真缺陷

首轮实测 **7/9**，两个失败项中一个是评测 mock 自身错误（注入表 fn 应直接返回
数据本体，双层 `{ok, data}` 包装导致 as_of 回填断裂），另一个是**真缺陷**：

> **E5「部分失败未如实标注」**：多步研究中某工具失败时，该步骤被静默丢弃——
> answer 的引用列表只含成功步，用户看不出哪个数据源挂了、为什么缺一块。
> 这正是本项目「静默吞失败」缺陷族在智能体层的再现（与 R2/R7 先例同型：
> 用户拿着残缺结果当完整结论）。

修复：run_research 汇总阶段把 error/rejected 步骤的原因回填进 limitations
（→ 合成器 answer 的 ⚠️ 行），失败原因从此必达用户。修复后 9/9，且既有
`tests/test_research_agent.py` 契约全绿（未破坏 T-268/T-271 已钉行为）。

## 3. 结论

- 智能体的「可信度」不由单次回答质量决定，而由**失败时的行为**决定：不编造
  （E4）、失败必达（E5 修复）、写操作拒执行（E6）、有界不挂死（E7–E9）。
- 方法论上，把「诚实语义」从人工审查转化为**可重跑的对抗性评测集**（9 题
  亚秒级完成），是本项目质量保障体系从页面守卫向 Agent 行为守卫的延伸。
- 边界：本评测覆盖规则合成器路径；LLM 措辞质量需要在线评估（留待后续工作），
  不在本文离线评测范围内，如实说明。

## 复现

```bash
python scripts/agent_eval_suite.py    # → reports/research_agent_eval.json（9 题）
pytest tests/test_research_agent_eval.py -q   # 守卫与套件同源
```
