# QuantAgent（modules/quantagent）

多智能体 A股投研框架，**构建于 StockSignal 的 `modules/` 数据/分析层之上**。

## 结构
```
quantagent/
├── __init__.py          导出 run_research / build_graph / run_research_langgraph / run_research_crewai / FinRAG / ChromaRetriever / BrowserAgent / progress
├── state.py             ResearchState 共享状态（贯穿状态图）+ DataFrame 注册表（resolve_df）+ 实时进度回调 reporter
├── llm.py               LLM 接入（复用 modules.llm_client，离线安全）
├── progress.py          多智能体「实时协作进度」共享定义（AGENT_FLOW / DEBATE_STAGES / percent_for / label_for）
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
├── crewai_orchestrator.py     CrewAI 多首席辩论编排（牛/熊/风控派对抗 + 主持合成，规则降级）
└── demo.py              离线冒烟测试（覆盖四件套 + crewai）
```

## 快速开始
```python
import sys
sys.path.insert(0, "/path/to/StockSignal")   # 确保 modules 在 sys.path
from modules.quantagent import run_research, format_report

# engine: "auto" | "langgraph" | "simple" | "crewai"
#  - auto: 装了 LangGraph 用真实编排，否则回退 simple
#  - crewai: 多首席辩论（牛/熊/风控派对抗 + 主持合成）
state = run_research("600519", engine="crewai", progress_callback=lambda s, m: print(s, m))
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

## 本轮新增（实时进度 + CrewAI 辩论 + 在线演示）
5. **多智能体实时协作进度**（前端精致进度条）
   - `modules/quantagent/progress.py`：前后端共用的 stage 语义（`AGENT_FLOW` / `DEBATE_STAGES` / `percent_for`）；
   - `state.add_trace` 自动触发 `reporter(stage, message)` 进度回调；
   - 后端 `backend/tasks/progress_bus.py` + `worker._run_task` 把进度写入 `task.stage / logs / progress`（节流落盘）；
   - `pages/Q_QuantAgent投研.py` 渲染「每个 Agent 独立进度条 + 实时日志流 + CrewAI 辩论面板」，暗色终端风，轮询不阻塞。
6. **CrewAI 多首席辩论**（`crewai_orchestrator.py`，`engine="crewai"`）
   - 协作范式：`5 分析智能体`（事实层）→ `🐂牛派 / 🐻熊派 / 🛡️风控派` 各自基于事实给出立场 → `⚖️主持首席` 综合裁定；
   - 真实 CrewAI 可用（装了 `crewai` 且配 LLM）时走 LLM 对抗，否则**规则辩论降级**（结构一致、说理清晰）；
   - 结论写入 `state.debate`（四派立场），并纳入 `chief_report`。
7. **在线演示页（CloudStudio）**
   - `deploy_preview/index.html`：自包含静态页，内嵌一次真实 600519 投研的进度事件序列与完整报告，
     纯前端回放「多智能体协作进度条 + 辩论 + 结论」，无需后端即可在线演示；
   - 部署链接：`https://dcf0fb6ef03e4ccaa0ba139b3b07a3a5.app.codebuddy.work`。

## 设计要点
- **复用优先**：所有分析逻辑直接 import StockSignal 的 `fetcher/technical/signal/news/backtest`，不重写。
- **离线可跑**：网络/Key 缺失时自动合成数据 + 规则引擎兜底，骨架永不断链。
- **可替换组件**：编排（自实现图 ↔ LangGraph ↔ CrewAI）、LLM（modules.llm_client）、采集（FinBrowser/browser-use）、
  检索（TF-IDF ↔ chromadb）均为可替换抽象，且均带优雅降级。

### 环境依赖（按需安装，缺则自动降级）
```bash
pip install langgraph      # 真实多智能体编排 + 条件路由 + HITL
pip install crewai         # 多首席辩论（真实 LLM 对抗，需配合 LLM key）
pip install chromadb       # 研报/决策的向量检索（需本地可启动 chroma 后端）
pip install browser-use playwright && playwright install   # FinBrowser 真实浏览器自动化（还需注入 LLM）
```
> 注：chromadb 1.5.x 的向量索引依赖原生 HNSW 后端（`hnswlib` 或 rust bindings），本沙箱无编译器/预编译
> wheel，故 FinRAG 自动回退 TF-IDF；但已为 `ChromaRetriever` 配置**零下载的本地 embedding**
> （`LocalEmbeddingFunction`，哈希向量 + L2 归一化），在具备 hnswlib/rust 的真实机器上即可离线启用向量检索，
> 无需下载默认 onnx 模型。browser-use 同理在未装/无 LLM 时回退 requests/mock。

详见上层技术方案文档：`QuantAgent技术方案.md`（在 hzz 工作区）。
