---
name: market_temperature
displayName: 市场情绪温度计·A股温度
slug: market-temperature
version: 1.0.0
description: "市场情绪温度计：调用 StockSignal modules.market_temperature，把牧羊人 8 项广度指标合成 0-100 市场温度（冰点/偏冷/中性/活跃/狂热五档），给出当日各指标贡献明细、极端区信号（仅恐慌出清→次日红盘一条有统计依据）与历史相似日。取不到数据即返回不可用状态，绝不编造温度值，不构成投资建议。"
agent_created: true
---

# 市场情绪温度计（A股 · 0-100 温度 + 五档 + 极端区）

## 这个 skill 解决什么

StockSignal 已有情绪**极值**信号（`modules/sentiment_edge.py`，唯一可发布规律是
「极端恐慌 → 次日红盘」），但**没有日常温度读数**：老板每天想知道「现在市场是冷是热」，
需要的是**描述性**的温度与分档，而不是方向预测。

本 skill 把 `modules/market_temperature.py` 封装成可独立调用的技能：
牧羊人 8 项广度指标 → 经验分位打分（跨年代可比）→ 0-100 综合温度 → 五档分档 →
各指标贡献明细 → 极端区信号 → 全历史相似日。

## 能力

输入当日 A 股广度数据（或自动从 StockSignal 取），输出：

| 字段 | 含义 |
|---|---|
| `temperature` | 0-100 综合温度（`shepherd_temperature` 经验分位合成） |
| `band` | 五档：冰点(<20) / 偏冷(20-40) / 中性(40-60) / 活跃(60-80) / 狂热(≥80)，含 `advice` |
| `contributions` | 各指标对温度的贡献明细 |
| `extreme` | 极端区信号：仅「恐慌出清 → 次日红盘」有全历史统计依据，其余诚实弃权 |
| `analogs` | 全历史广度向量最近相似日（描述类比，**不是预测**） |

## 用法

```bash
# 自动发现 StockSignal（环境变量 STOCKSIGNAL_ROOT 或同机相对位置）
python scripts/query_temperature.py

# 指定 StockSignal 根目录
python scripts/query_temperature.py --stock-signal-root E:/project/ks/StockSignal

# 用本地广度 JSON（离线可用）
python scripts/query_temperature.py --today-json today_breadth.json
```

输出为 JSON；`available=false` 时附 `reason`，**不返回任何编造的温度值**。

## 诚实边界（写进产品页，不藏）

1. **温度是描述性指标，不是预测指标**。它说「现在市场很冷」，不说「明天会涨」。
2. **五档阈值与 StockSignal 完全一致**：`lib/temperature_engine.py` 优先调用
   `modules.market_temperature`（单一真理源），读不到才用内置镜像并标 `degraded=true`。
3. **极端区只有一条可发布规律**：`sentiment_edge.panic_reversal`（极端恐慌 → 次日红盘，
   全历史 296 天 z=+4.36）。其余时刻**明确弃权**，不硬猜方向。
4. **相似日是描述不是预测**：历史相似 ≠ 明天必然如此，不含任何前视泄漏。
5. 不构成投资建议。

## 适用场景 / 常见疑问 / 反模式 / 快速示例
- **适用场景**：见上方 SKILL.md 正文（受众 + 触发词 + 能力边界）。
- **常见疑问**：没有 StockSignal 能用吗？→ 能，用 `--today-json` 喂本地广度 JSON；
  但此时温度合成缺少全历史分位基准，引擎会标 `degraded` 并说明。
- **反模式**：不要把温度当买卖信号；温度到极值往往是风险提示而非加仓信号。
- **快速示例**：见 SKILL.md 中的命令 / 脚本用法与模板。
