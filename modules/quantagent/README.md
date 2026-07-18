# QuantAgent（modules/quantagent）

多智能体 A股投研框架，**构建于 StockSignal 的 `modules/` 数据/分析层之上**。

## 结构
```
quantagent/
├── __init__.py          导出 run_research / build_graph / run_research_langgraph / FinRAG / ChromaRetriever / BrowserAgent
├── state.py             ResearchState 共享状态（贯穿状态图）+ DataFrame 注册表（resolve_df）
├── llm.py               LLM 接入（复用 modules.llm_client，离线安全）
├── browser_plugin.py    组件⑤ FinBrowser 采集外挂（BrowserAgent：browser-use 真实 / requests 兜底）
├── rag_module.py        组件④ FinRAG 记忆/RAG 模块（ChromaRetriever 向量库 / Retriever TF-IDF 双检索）
├── agents/
│   ├── base.py          Agent 抽象基类（防御式调用约定）
│   ├── data_agent.py     数据工程师（产出行情 df 并存入注册表）
│   ├── fundamental_agent.py 基本面分析师
│   ├── technical_agent.py   技术分析师（resolve_df 取行情）
│   ├── sentiment_agent.py   舆情分析师（+ FinBrowser）
│   ├── risk_agent.py        风控官（resolve_df 取行情）
│   └── chief_agent.py       首席投研官（综合决策 + 写记忆）
├── orchestrator.py      零依赖状态图编排（fallback）+ run_research 引擎分发器
├── langgraph_orchestrator.py  真实 LangGraph 编排（条件路由 + 人工审批 HITL）
└── demo.py              离线冒烟测试（覆盖四件套）
```

## 快速开始
```python
import sys
sys.path.insert(0, "/path/to/StockSignal")   # 确保 modules 在 sys.path
from modules.quantagent import run_research, format_report

# engine: "auto"(装了 LangGraph 用真实编排，否则回退) | "langgraph" | "simple"
state = run_research("600519", engine="auto")
print(format_report(state))
```

## 四大增强（相对初版）
1. **真实 LangGraph 编排**（`langgraph_orchestrator.py`）
   - 用 `langgraph.graph.StateGraph` 实现多智能体有向图，含 `MemorySaver` checkpointer。
   - **条件路由**：`risk_gate` 按风控评分分流——高风险（或 `force_human_review`）转入「人工复核」节点。
   - **人工审批 HITL**：`human_approval` 节点用 `langgraph.types.interrupt()` 暂停，外部以
     `Command(resume={"approved": bool, "note": str})` 恢复（配合 checkpointer 可断点续跑）。
   - DataFrame 经**注册表**跨节点传递，LangGraph 快照彻底排除 df，规避 checkpointer 序列化坑
     （另附 `_SafeSerde` 容错序列化器兜底）。
2. **FinBrowser 升级 browser-use**（`browser_plugin.py`）
   - 真实模式用 `browser_use.Agent` 做 LLM 驱动的浏览器自动化；
   - 未装/无 LLM 时自动回退 `requests` 采集 + 离线 mock，链路永不断。
   - 统一入口 `BrowserAgent`，与 `sentiment_agent` 接口兼容。
3. **FinRAG 检索层换 chromadb**（`rag_module.py`）
   - `ChromaRetriever`：chromadb 持久化向量检索，支持大规模研报/历史决策语料库；
   - `use_chroma=True`（默认）且 chromadb 可用时自动启用，**否则回退 TF-IDF**；
   - 记忆层 `MemoryStore`（episodic/semantic）始终启用，跨会话持久化。
4. **接入后端任务 + 轮询通道**（StockSignal Flask 5050）
   - 后端 `backend/tasks/worker.py` 注册 `quant_research` handler；
   - `backend/api/task_routes.py` 白名单放行 `quant_research`；
   - 前端 `pages/Q_QuantAgent投研.py` 改为「提交任务 → fragment 轮询」，**不阻塞 UI**；
   - handler 返回 `state.to_dict()`（已剔除 DataFrame），可直接 JSON 序列化。

## 设计要点
- **复用优先**：所有分析逻辑直接 import StockSignal 的 `fetcher/technical/signal/news/backtest`，不重写。
- **离线可跑**：网络/Key 缺失时自动合成数据 + 规则引擎兜底，骨架永不断链。
- **可替换组件**：编排（自实现图 ↔ LangGraph）、LLM（modules.llm_client）、采集（FinBrowser/browser-use）、
  检索（TF-IDF ↔ chromadb）均为可替换抽象，且均带优雅降级。

### 环境依赖（按需安装，缺则自动降级）
```bash
pip install langgraph      # 真实多智能体编排 + 条件路由 + HITL
pip install chromadb       # 研报/决策的向量检索（需本地可启动 chroma 后端）
pip install browser-use playwright && playwright install   # FinBrowser 真实浏览器自动化（还需注入 LLM）
```
> 注：本沙箱（无正常 certs/网络）下 chromadb 本地后端无法启动，FinRAG 自动回退 TF-IDF；
> browser-use 同理在未装/无 LLM 时回退 requests/mock。生产机器装好依赖即自动启用。

详见上层技术方案文档：`QuantAgent技术方案.md`（在 hzz 工作区）。
