---
name: 连板龙头共振
description: "股票（A股）类型的连板接力分析技能：读取每日连板梯队分布，跨日递推各档晋级率（首板→二板、二板→三板……），输出综合晋级率与置信度。核心口径是「首板→二板晋级率」，被认为是接力意愿最纯粹的度量；历史样本≥10 天时输出 actionable 信号，不足或数据缺失时明确降级，不编造信号、不驱动决策。支持自动读取 StockSignal 历史、手动传入今日分布、历史回填三种用法。纯本地计算、零网络、不写不删文件。"
agent_created: true
---

# 连板龙头共振

## 能力

输入当日 A 股连板梯队分布（各板家数），或自动读取 StockSignal 的 `data/shepherd_ladder_history.json`，
计算各档晋级率：

- `2b` = 今日 2 板家数 / 昨日首板家数（最核心）
- `3b` = 今日 3 板家数 / 昨日 2 板家数
- 依此类推

综合晋级率优先取 `2b`；`2b` 缺失时取可用档均值。

## 用法

```bash
# 自动从 StockSignal 历史读取
python <skill>/scripts/ladder_resonance.py --auto

# 给定今日梯队分布（JSON 格式：档位 -> 家数）
python <skill>/scripts/ladder_resonance.py --today '{"1": 45, "2": 12, "3": 3, "4": 1}'

# 历史回填口径：只用到某一日为止的数据
python <skill>/scripts/ladder_resonance.py --date 2026-09-30

# 查看数据边界与诚实口径
python <skill>/scripts/ladder_resonance.py --summary
```

## 输出示例

```json
{
  "available": true,
  "ready": true,
  "days": 47,
  "latest_date": "2026-09-30",
  "rates": {
    "2b": 26.7,
    "3b": 25.0,
    "4b": 33.3
  },
  "overall": 26.7,
  "actionable": true,
  "confidence": "medium",
  "source": "E:/project/ks/StockSignal/data/shepherd_ladder_history.json"
}
```

## 能力边界

- ✅ **可信**：历史 ≥10 天的首板→二板晋级率，可描述当前接力强度。
- ⚠️ **低可信**：历史 2–9 天返回 `confidence="low"`、`actionable=false`，仅供展示。
- ❌ **不可信**：无历史或分布缺失时返回 `available=false`，不编造晋级率。
- ❌ 不输出具体个股、不提供买卖点，仅描述市场接力结构。

## 数据依赖

- 优先读取环境变量 `STOCKSIGNAL_ROOT` 指向的 StockSignal 仓库：
  `<STOCKSIGNAL_ROOT>/data/shepherd_ladder_history.json`
- 可通过 `SS_LADDER_FILE` 环境变量重定向路径。
-  standalone 运行但无数据时只返回不可用的诚实状态。

## 安全与权限

- **只读**：仅读取上述 JSON 文件。
- **零网络**：无 requests / urllib / socket。
- **零写删**：不写用户文件、不删除文件、不修改配置。
- **零密钥**：不读取任何密钥/令牌类环境变量。
