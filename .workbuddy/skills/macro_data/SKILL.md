---
name: 宏观数据
displayName: 宏观数据·全球风险评分
slug: macro-data
version: 1.1.0
description: "宏观指标取数：调用 StockSignal modules.macro_data，覆盖国内 PMI/CPI/PPI/GDP/M2/LPR 与全球 12 项指标，合成 0-100 全球宏观评分。取不到返回 None 绝不填合成值；规则解读非 AI 洞见，失败即诚实降级。"
agent_created: true
---

# 宏观指标（国内 + 全球 · 取数与规则化解读）

## 这个 skill 解决什么
StockSignal 的功能表早就写了「宏观数据 | PMI、CPI、社融等关键宏观指标」，但长期没有对应实现——
属于**说了却没做**的空白。`modules/macro_data.py` 把这块补上了，并额外补齐了老板要求的**全球维度**：

- **国内 6 项**：PMI / CPI / PPI / GDP / M2 / LPR（国家统计局、央行）。
- **全球 12 项**：美国 ISM PMI / 非农 / 失业率 / CPI / PPI / GDP、美债 10Y、美元兑人民币、美元指数 DXY、标普500 / 纳斯达克 / 恒生。
- **`global_regime_score()`**：把全球分项规则化合成一个 0-100 的「全球流动性 / 风险偏好」评分，
  作为 A 股外部环境的量化输入。

## 何时用
- 用户问"现在宏观怎么样""PMI 多少""美债收益率""美元指数""全球流动性对 A 股友好吗"。
- 用户要写晨报 / 策略，需要把宏观景气与政策变量作为背景输入。

## 用法（让 AI 执行命令，不要自己编数字）
通过命令行调用自带脚本（需 `akshare` 且联网取数）：

```bash
# 1) 单个指标
python <skill目录>/scripts/query_macro.py indicator pmi
python <skill目录>/scripts/query_macro.py indicator us_treasury_10y

# 2) 按区域取（国内 / 全球）
python <skill目录>/scripts/query_macro.py region 国内
python <skill目录>/scripts/query_macro.py region 全球

# 3) 全部指标
python <skill目录>/scripts/query_macro.py all

# 4) 全球宏观风险偏好评分（0-100）
python <skill目录>/scripts/query_macro.py regime
```

- 脚本通过 `STOCKSIGNAL_ROOT` 环境变量（默认 `E:/project/ks/StockSignal`）定位仓库，
  动态导入 `modules.macro_data`（**单一真理源**）。
- 取数走 `akshare`，需联网；**取不到即返回 `None`**，脚本如实打印 `null`，绝不填合成值。

## 输出与诚实口径（务必照实呈现给用户）
- `fetch_indicator(key)` 成功返回 `{"key","name","value","prev","change","date","source","region",...}`；
  失败返回 `None`。
- `global_regime_score()` 返回 `{"score": 0-100, "sub": {...各分项分}, "parts": {...原始值}}`；
  全部分项取不到返回 `None`。
- `interpret(key, value, prev)` 是**确定性规则**（一行 if/else），**不是大模型生成**——
  展示时必须如实标注"规则解读"，**严禁把它包装成 AI 洞见**（那也是一种造假）。

## 能力边界（写进产品/回答，不藏）
- ✅ 可信：18 项指标的**真实最新值 + 环比 + 数据日期**；全球风险评分的分项折算逻辑完全透明。
- ❌ 不可信：网络不通 / akshare 接口变更 / 某指标缺失时，对应项返回 `None`，请勿脑补。
- ⚠️ 评分是**规则化合成**（DXY 中枢 100、美债 10Y 中枢 4.0%、美国 CPI 中枢 3.0%、USD/CNY 中枢 7.1），
  是粗粒度宏观环境温度计，不是预测模型。

## 红线
- **取不到就返 None，绝不填合成数据、绝不默认 0**。
- 规则解读与全球评分必须标注"规则生成 / 非 AI"，不得伪装成智能洞察。
- 每次数值必须带真实数据日期；陈旧数据须如实标注，不装作实时。
- 不读密钥、不写用户文件、不删文件。

---

## 适用场景 / 常见疑问 / 反模式 / 快速示例
- **适用场景**：见上方 SKILL.md 正文（受众 + 触发词 + 能力边界）。
- **常见疑问**：数据取不到怎么办？→ 严守诚实口径，取不到即返回 None / 不可用状态，绝不填合成值或编造信号。
- **反模式**：不要期望它在样本不足时给 actionable 信号；超出能力边界时它会诚实降级，而非编造。
- **快速示例**：见 SKILL.md 中的命令 / 脚本用法与模板。
