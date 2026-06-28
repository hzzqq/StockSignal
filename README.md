<div align="center">

# StockSignal · A股事件驱动投资分析平台

**软件工程实训课程设计**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Pandas](https://img.shields.io/badge/Pandas-2.0+-green?logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 基于事件驱动策略的 A 股数据分析工具，聚合产业事件、价格信号与宏观催化三类数据，  
> 辅助投资者识别主线行情、回测交易策略、追踪仓位盈亏。

</div>

---

## 目录

- [项目简介](#项目简介)
- [功能模块](#功能模块)
- [系统架构](#系统架构)
- [目录结构](#目录结构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [模块说明](#模块说明)
- [数据来源](#数据来源)
- [开发计划](#开发计划)
- [作者](#作者)

---

## 项目简介

StockSignal 是一款面向个人投资者的 **A 股事件驱动分析工具**，通过整合三类核心催化信号：

| 类型 | 说明 | 示例 |
|------|------|------|
| 产业事件 | 政策发布、行业并购、产能变化 | 光伏装机补贴、半导体设备禁令 |
| 价格信号 | 大宗商品、上游原材料价格变动 | MLCC 涨价、煤炭港口价格 |
| 宏观数据 | PMI、CPI、社融等关键宏观指标 | PMI 超预期 → 顺周期主线 |

帮助用户**快速识别行情主线**、**可视化行业轮动**、**回测简单的事件驱动策略**。

---

## 功能模块

### 模块 1 — 数据采集与预处理

- 对接 AKShare / Tushare 接口，自动拉取股票行情、财务数据、宏观指标
- 本地 SQLite 缓存，避免重复请求
- 数据清洗：缺失值处理、复权调整、异常值识别

### 模块 2 — 行情可视化

- 交互式 K 线图（ECharts / mplfinance）
- 自定义叠加：均线、MACD、RSI、成交量
- 行业板块涨跌热力图（Sector Heatmap）
- 个股与指数相关性矩阵

### 模块 3 — 事件信号追踪

- **新闻自动挖掘**：一键抓取东方财富/财新/央视新闻，jieba 关键词提取，金融情感分析，自动入库
- 关键词订阅：输入关键词（如"煤炭""MLCC"）自动匹配相关事件
- 事件时间轴：将重大事件标注在 K 线图上，直观展示事件前后行情变化
- 信号打分：综合价格（40%）、事件（40%）、宏观（20%）三类信号，输出 0-100 分的主线强度得分
- 情感分析报告：新闻情感分布饼图、热门关键词 TOP15、正负面新闻样本

### 模块 4 — 策略回测

- 内置事件驱动 + 均线交叉两种策略
- 事件驱动策略融合实时新闻情感打分
- 输出：累计收益曲线、最大回撤、夏普比率、胜率统计

### 模块 5 — 仓位管理看板

- 记录持仓成本、当前市值、浮动盈亏
- 盈亏归因：哪个事件/板块贡献了涨幅
- 导出 Excel 持仓报告

---

## 系统架构

```
用户界面（Streamlit Dashboard）
        │
        ▼
   业务逻辑层
  ┌────────────────────────────────────────┐
  │  数据采集  │  信号分析  │  策略回测     │
  └────────────────────────────────────────┘
        │
        ▼
   数据存储层
  ┌─────────────────────────────┐
  │  SQLite（行情/事件缓存）     │
  │  CSV（自定义持仓记录）       │
  └─────────────────────────────┘
        │
        ▼
  外部数据接口
  AKShare  /  Tushare  /  公开新闻 RSS
```

---

## 目录结构

```
StockSignal/
├── app.py                  # Streamlit 主入口
├── config.yaml             # 全局配置（API token、默认参数）
├── requirements.txt        # 依赖包列表
├── README.md
│
├── data/                   # 本地数据存储
│   ├── cache.db            # SQLite 行情缓存
│   ├── portfolio.csv       # 用户持仓记录
│   └── events.csv          # 用户自定义事件记录
│
├── modules/
│   ├── fetcher.py          # 数据采集模块（AKShare/Tushare 封装）
│   ├── cleaner.py          # 数据清洗与预处理
│   ├── signal.py           # 事件信号识别与评分（集成新闻情感）
│   ├── news.py             # 新闻挖掘（抓取+jieba关键词+金融情感分析）
│   ├── visualizer.py       # 图表生成（K线、热力图、相关性）
│   ├── backtest.py         # 策略回测引擎
│   └── portfolio.py        # 仓位管理与盈亏统计
│
├── pages/                  # Streamlit 多页面
│   ├── 1_行情看板.py
│   ├── 2_事件追踪.py        # 含新闻挖掘 + 情感分析报告
│   ├── 3_策略回测.py
│   └── 4_仓位管理.py
│
└── tests/                  # 单元测试
    ├── test_fetcher.py
    ├── test_signal.py
    ├── test_news.py
    └── test_backtest.py
```

---

## 技术栈

| 类别 | 库 / 工具 | 版本 | 用途 |
|------|-----------|------|------|
| 数据采集 | AKShare | ≥ 1.12 | A 股行情、宏观数据免费接口 |
| 数据处理 | Pandas | ≥ 2.0 | 数据清洗、时间序列处理 |
| 数值计算 | NumPy | ≥ 1.26 | 指标计算、回测统计 |
| 可视化 | Matplotlib / mplfinance | ≥ 3.8 | K 线、走势图 |
| 可视化 | Plotly | ≥ 5.20 | 交互式图表、热力图 |
| 界面框架 | Streamlit | ≥ 1.35 | 本地 Web 看板，无需前端开发 |
| 数据库 | SQLite3 | 内置 | 行情数据本地缓存 |
| NLP 分词 | jieba | ≥ 0.42 | 新闻关键词提取（TF-IDF + TextRank 融合） |
| 情感分析 | SnowNLP | ≥ 0.12 | 中文情感分析兜底（金融词典优先） |
| 测试 | pytest | ≥ 8.0 | 单元测试 |
| 导出 | openpyxl | ≥ 3.1 | 持仓报告导出 Excel |

> **Python 版本要求：** ≥ 3.10

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/<your-username>/StockSignal.git
cd StockSignal
```

### 2. 创建虚拟环境

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置参数（可选）

编辑 `config.yaml`，填入 Tushare Token（免费注册获取），AKShare 无需 Token。

```yaml
tushare:
  token: "YOUR_TUSHARE_TOKEN_HERE"   # 可选，不填则只用 AKShare

default:
  market: "A股"
  cache_days: 7                       # 缓存有效天数
```

### 5. 启动应用

```bash
streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`，即可使用全部功能。

---

## 模块说明

### fetcher.py — 数据采集

```python
from modules.fetcher import StockFetcher

fetcher = StockFetcher()
# 拉取单只股票日线行情（自动复权）
df = fetcher.get_daily("600519", start="2024-01-01", end="2025-06-01")
# 拉取宏观数据：PMI
pmi = fetcher.get_macro("pmi_mfg")
```

### signal.py — 事件信号评分

```python
from modules.signal import SignalEngine

engine = SignalEngine()
score = engine.evaluate(
    ticker="601088",       # 中国神华
    event_keywords=["煤炭", "电厂库存", "保供"],
    date="2026-06-28"
)
# 返回 {"price_score": 72, "event_score": 85, "macro_score": 60, "total": 73}
```

### backtest.py — 策略回测

```python
from modules.backtest import Backtester

bt = Backtester(
    ticker="000858",
    start="2023-01-01",
    end="2025-12-31",
    strategy="event_driven",
    params={"entry_score": 70, "exit_score": 40}
)
result = bt.run()
print(result.summary())
# 累计收益: +38.5%  最大回撤: -12.3%  夏普比率: 1.42
```

---

## 数据来源

| 数据类型 | 来源 | 是否免费 | 说明 |
|----------|------|----------|------|
| A 股日线行情 | [AKShare](https://akshare.akfamily.xyz/) | 免费 | 无需注册，直接调用 |
| 财务数据 | [Tushare](https://tushare.pro/) | 注册免费 | 注册后获取 Token |
| 宏观指标 | AKShare | 免费 | PMI、CPI、社融等 |
| 大宗商品价格 | AKShare | 免费 | 煤炭、螺纹钢、MLCC 等 |
| 新闻事件 | 东方财富 RSS | 免费 | AKShare 封装接口 |

---

## 开发计划

| 阶段 | 任务 | 状态 |
|------|------|------|
| Week 1 | 需求分析、技术选型、项目初始化 | ✅ 已完成 |
| Week 2 | 数据采集模块（fetcher + cleaner） | ✅ 已完成 |
| Week 3 | 行情可视化（K 线 + 热力图） | 🚧 进行中 |
| Week 4 | 事件信号追踪与评分 | ⬜ 待开始 |
| Week 5 | 策略回测引擎 | ⬜ 待开始 |
| Week 6 | 仓位管理看板 | ⬜ 待开始 |
| Week 7 | 测试、文档、答辩准备 | ⬜ 待开始 |

---

## 作者

| 姓名 | 学号 | 负责模块 |
|------|------|----------|
| hzz | XXXXXXXX | 全部模块（个人项目） |

---

<div align="center">

**本项目为软件工程实训课程设计，仅用于学习研究，不构成任何投资建议。**

</div>
