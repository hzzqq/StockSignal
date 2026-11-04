---
name: 事件因子
displayName: 事件因子·A股信号
slug: event-factor
version: 1.0.2
description: "事件因子查询：调用 StockSignal modules.event_factor，从五个真实源（P1 EV 模型 / 东方财富新闻情感 / 龙虎榜 / 本地事件主表 / 用户语音转写事件）兜底取真实信号，可选附加全球宏观上下文，判断个股看多/看空与百分位。取不到即 available=False，绝不编造或默认 0；支持单标查询与事件驱动看多榜。"
agent_created: true
---

# 事件因子（个股 · 事件/regime 信号）

## 这个 skill 解决什么
老板的 StockSignal 项目需要一个「事件因子适配器」把量化特征对接到**真实信号源**，而不是合成演示数据。
`modules/event_factor.py` 就是这个适配器：

五个真实源按兜底序（互不替代、绝不造数）：
1. **P1-QuantFactor EV 模型**（38 维量价 + 牧羊人市场广度情绪 9 维 = 47 维，含事件 / regime 通道）；
2. **东方财富个股新闻情感**（`news_event_signal`，逐标的真实事件面）；
3. **东方财富龙虎榜上榜信号**（`lhb_event_signal`，游资 / 机构关注度）；
4. **本地事件追踪主表**（`tracked_event_signal`，data/events.csv：人工录入 + 语音入库沉淀事件）；
5. **用户语音转写事件**（`voice_event_signal`，data/voice_events/<username>.json）——
   仅当调用方显式传入 `voice_user`（登录用户）时启用，**隐私闸门强制绝不跨用户读桶**。

可选的**全球宏观上下文**（`include_macro=True`）：复用 `modules.macro_data` 的真实 akshare 指标
（美债 10Y/2Y、DXY、USD/CNY、美联储利率、CPI/PPI/GDP、美股/港股等）规则化合成 0-100
风险偏好分，每个数值带**真实数据日期**。**只作上下文展示，绝不参与事件因子评分**
（避免未回测口径耦合）；取不到即 `None`，绝不填充合成值。

设计纪律与项目红线一致：**取不到就 `available=False` 并说明原因，绝不返回合成 / 随机值**。

## 何时用
- 用户问"这只票有没有事件因子信号""这标的是看多还是看空""事件驱动看多榜有哪些票"。
- 用户在跑策略 / 写研报，需要把"事件因子"作为一条可解释、有真实来源的特征。

## 用法（让 AI 执行命令，不要自己编数字）
通过命令行调用自带脚本（自带 Python 即可，无需额外依赖）：

```bash
# 1) 查询单标的事件因子（默认模型 ev）
python <skill目录>/scripts/query_event_factor.py symbol 600519
python <skill目录>/scripts/query_event_factor.py symbol 300750 --model ev

# 2) 启用第五源（仅当前登录用户自己的语音事件；不传则完全不读语音桶）
python <skill目录>/scripts/query_event_factor.py symbol 600519 --voice-user alice

# 3) 附加全球宏观上下文（联网取数，不参与评分；取不到如实标 unavailable）
python <skill目录>/scripts/query_event_factor.py symbol 600519 --include-macro

# 4) 取事件驱动看多榜（按真实事件因子排序的多头候选池）
python <skill目录>/scripts/query_event_factor.py longlist --top-n 20
```

- 脚本通过 `STOCKSIGNAL_ROOT` 环境变量（默认 `E:/project/ks/StockSignal`）定位 StockSignal 仓库，
  动态导入 `modules.event_factor`（**单一真理源**）；仓库不在则诚实报错而非编造。
- 若 P1 信号停更 / 标的不在池内，`get_event_factor` 会依次尝试后续真实源；全部无信号才返回
  `available=False` 并给出原因——这是预期行为，请如实告知用户，不要伪装成有信号。
- 五个源都取不到时返回结构里**不含** `score`/`rank`/`signal` 键（绝不塞占位分数）。

## 输出与诚实口径（务必照实呈现给用户）
`get_event_factor` 返回结构：
- **有数据**：`{"available": True, "symbol", "score", "signal": "看多"|"看空", "rank", "date", "source"}`
- **无数据**：`{"available": False, "symbol", "reason": "..."}`（如"该标的无 P1 事件因子信号"）

`event_driven_long_list` 返回列表，每项 `{"symbol", "score"(0-100 百分位), "raw_rank", "raw_pred", "signal":"看多", "source"}`；
取不到真实信号优雅返回 `[]`，调用方应展示"无信号"提示而**不应报错或填充假值**。

## 能力边界（写进产品/回答，不藏）
- ✅ 可信：五源均为真实数据（P1 EV ranked 信号 / 东财新闻 / 龙虎榜 / 本地事件主表 / 用户语音），
  宏观上下文分项各带真实数据日期。
- ❌ 不可信 / 不可用：五源全部取不到、数据源异常——一律 `available=False`，不硬猜。
- ⚠️ 语音源**默认关闭**（须显式 `voice_user`），宏观上下文**默认关闭**（须显式 `include_macro`），
  二者都不会悄悄联网或跨用户读数据。
- ⚠️ 宏观上下文是**确定性规则合成的背景分**（非模型生成、非个股方向判定），展示时必须如实标注，
  不得包装成 AI 洞见；它**不参与**事件因子评分。
- ⚠️ 各源数据有效日可能滞后，使用前确认新鲜度；陈旧信号须如实标注。

## 红线
- **绝不外推到无依据的结论**，取不到就说取不到，不要为了显得有用而编造方向或分数。
- 不读密钥、不写用户文件、不删文件；`news/lhb` 与 `--include-macro` 会按用户显式请求联网取真实数据
  （默认不触发），其余路径纯只读本地文件。
- 若返回 `available=False`，措辞必须保留"暂无真实信号 / 数据不足"。

---

## 适用场景 / 常见疑问 / 反模式 / 快速示例
- **适用场景**：见上方 SKILL.md 正文（受众 + 触发词 + 能力边界）。
- **常见疑问**：数据取不到怎么办？→ 严守诚实口径，取不到即返回 available=False / None，绝不编造或默认 0。
- **反模式**：不要期望它在样本不足时给 actionable 信号；超出能力边界时它会诚实降级，而非编造。
- **快速示例**：见 SKILL.md 中的命令 / 脚本用法与模板。
