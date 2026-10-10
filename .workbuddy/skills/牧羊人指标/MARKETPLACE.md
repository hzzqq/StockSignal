# 牧羊人指标 · 技能简介（Marketplace Blurb）

---

## 中文简介

**名称**：牧羊人指标（股票 / A股 类型情绪指标）

**一句话**：输入当日 A 股涨跌停广度，基于全历史 walk-forward 校准，告诉你「明天该不该看涨」——但只在**极端恐慌**时才敢说话。

**为什么值得装**
普通日子的次日涨跌方向，经 2007–2026 全历史检验根本无法超越随机基准（情绪评分与次日收益 IC≈-0.031，纯噪声）。所以绝大多数「情绪判明天」的工具都在硬猜。
这个技能反其道而行：**只对一条被严格验证的规律表态**——

> 极端恐慌（跌停占比冲到历史前 10%）→ 次日红盘概率 **62.5%**，显著高于 49.8% 基准，z=+4.36，296 天样本。

其余日子一律**诚实弃权**，绝不为了显得有用而编一个偏多/偏空。

**触发词**：明天行情、次日涨跌、恐慌反弹、牧羊人情绪、极端恐慌、次日怎么走、判断第二天、情绪极值信号。

**用法**
```bash
# 给定今日数据（涨跌家数 / 跌停 / 触及跌停 / 涨停）
python <skill>/scripts/next_day_edge.py --today '{"up_count":2000,"down_count":2900,"flat_count":100,"limit_down":50,"touch_down":80,"limit_up":20}'
# 自动从 StockSignal 当日快照取数
python <skill>/scripts/next_day_edge.py --auto
# 查看这个规律为什么可信（校准证据链）
python <skill>/scripts/next_day_edge.py --summary
```

**能力边界（写进产品，不藏）**
- ✅ 可信：极端恐慌 → 次日红盘概率显著高于基准（约 +13pp，全历史 296 天 z=+4.36）。
- ✅ 弱可信：触及跌停占比与次日**波动幅度**弱正相关（IC≈0.13~0.16）→ 仅作风险提示。
- ❌ 不可信：普通日子里次日方向（现有引擎无法超越基准率，本技能不硬猜）。

**安全**：纯本地计算、零网络外呼、不读密钥、不写用户文件、不删文件。校准件优先读取 StockSignal 仓库活数据，缺则回退自带冻结引擎，可独立运行。

---

## English Blurb

**Name**: Shepherd Indicator (Stock / A-share sentiment indicator)

**In one line**: Feed it today's A-share breadth (advancers/decliners, limit-up/limit-down counts); based on a full-history walk-forward calibration it tells you whether to lean bullish tomorrow — but it only speaks up on **extreme panic**.

**Why it's worth installing**
On ordinary days, next-day direction is statistically indistinguishable from a coin flip — across 2007–2026 the sentiment score's rank-IC vs next-day return is ≈ -0.031 (pure noise). Most "sentiment → tomorrow" tools are just guessing.
This skill does the opposite: it only commits to **one rigorously validated rule** —

> Extreme panic (limit-down ratio in the historical top 10%) → next-day up-day probability **62.5%** vs a 49.8% baseline, z=+4.36 over 296 trigger days.

On every other day it **honestly abstains** — no fabricated bullish/bearish call just to look useful.

**Trigger phrases**: tomorrow's market, next-day move, panic rebound, shepherd sentiment, extreme panic, how will tomorrow go, judge the next day, sentiment extreme signal.

**Usage**
```bash
python <skill>/scripts/next_day_edge.py --today '{"up_count":2000,"down_count":2900,"flat_count":100,"limit_down":50,"touch_down":80,"limit_up":20}'
python <skill>/scripts/next_day_edge.py --auto      # auto-read from StockSignal daily snapshot
python <skill>/scripts/next_day_edge.py --summary   # show the calibration evidence chain
```

**Capability boundaries (stated openly)**
- ✅ Trusted: extreme panic → next-day up probability well above baseline (~+13pp, 296 days, z=+4.36).
- ✅ Weak: touch-down ratio weakly correlates with next-day *volatility* (IC≈0.13~0.16) → risk hint only.
- ❌ Untrusted: next-day direction on ordinary days (no edge over baseline; the skill will not guess).

**Safety**: fully local, no network calls, no secret access, no file writes/deletes. Calibration is read live from the StockSignal repo when present, with a bundled frozen engine as fallback so it runs standalone.
