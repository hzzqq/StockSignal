"""
modules/quantagent/rag_module.py
---------------------------------
组件④ · FinRAG：金融记忆 / RAG 模块（首席决策 Agent 的「复盘大脑」）

两层能力，对应 Mem0 的设计理念：
  1) MemoryStore（记忆层）： episodic —— 该标的的历史决策；semantic —— 用户偏好。
     落盘到 data/quantagent_memory.json，跨会话持久化。
  2) Retriever（RAG 层）：轻量 TF-IDF 检索，从「研报/笔记语料库」召回相关片段。
     纯 Python 实现，零额外依赖；生产可平滑替换为 chromadb / LlamaIndex。

对外暴露 retrieve_context(ticker, query) 供 orchestrator 在首席决策前注入上下文。
"""

from __future__ import annotations

import json
import math
import os
import re
from typing import Dict, List

# 延迟导入 chromadb，保证模块在无依赖环境仍可 import（仅使用真实向量检索时才会真正用到）
try:
    import chromadb  # type: ignore
    _HAS_CHROMA = True
except Exception:  # pragma: no cover
    _HAS_CHROMA = False


# ---------- 轻量分词（中文按字+英文按词，零依赖）----------
def _tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    toks: List[str] = re.findall(r"[a-z0-9]+", text)
    # 中文字符逐个作为 token（演示级；生产可换 jieba）
    toks += [c for c in text if "\u4e00" <= c <= "\u9fff"]
    return [t for t in toks if len(t) > 0]


class Retriever:
    """极简 TF-IDF 检索器（无第三方依赖）。"""

    def __init__(self, corpus: List[Dict[str, str]] | None = None):
        self.docs: List[Dict[str, str]] = list(corpus or [])
        self._build()

    def _build(self):
        self.df: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_vecs: List[Dict[str, float]] = []
        n = max(1, len(self.docs))
        for d in self.docs:
            toks = _tokenize(d.get("text", ""))
            vec: Dict[str, float] = {}
            for t in toks:
                vec[t] = vec.get(t, 0.0) + 1.0
            for t in vec:
                self.df[t] = self.df.get(t, 0) + 1
            self.doc_vecs.append(vec)
        for t, c in self.df.items():
            self.idf[t] = math.log((n + 1) / (c + 1)) + 1.0

    def add(self, doc_id: str, text: str):
        self.docs.append({"id": doc_id, "text": text})
        self._build()

    @staticmethod
    def _tfidf_vec(vec: Dict[str, float], idf: Dict[str, float]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t, tf in vec.items():
            out[t] = (1 + math.log(tf)) * idf.get(t, 0.0)
        return out

    def search(self, query: str, k: int = 3) -> List[Dict[str, object]]:
        if not self.docs:
            return []
        q_toks = _tokenize(query)
        q_vec = self._tfidf_vec({t: q_toks.count(t) for t in set(q_toks)}, self.idf)
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
        scored = []
        for i, dvec in enumerate(self.doc_vecs):
            d_tfidf = self._tfidf_vec(dvec, self.idf)
            d_norm = math.sqrt(sum(v * v for v in d_tfidf.values())) or 1.0
            dot = sum(q_vec.get(t, 0.0) * d_tfidf.get(t, 0.0) for t in q_vec)
            sim = dot / (q_norm * d_norm)
            if sim > 0:
                scored.append({"id": self.docs[i].get("id", i), "text": self.docs[i]["text"], "score": round(sim, 3)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        if not scored and self.docs:
            # 查询与语料无词重叠（相似度全 0）时，至少返回前 k 条作为通用投研参考，
            # 避免「相关研报/笔记」段落永远为空。
            scored = [
                {"id": self.docs[i].get("id", i), "text": self.docs[i]["text"], "score": 0.0}
                for i in range(min(k, len(self.docs)))
            ]
        return scored[:k]


class ChromaRetriever:
    """
    基于 chromadb 的向量检索器（生产级）：支持大规模研报/历史决策语料库的持久化向量检索。

    与 Retriever(TF-IDF) 保持相同接口：add(doc_id, text) / search(query, k)。
    当 chromadb 可用且 FinRAG(use_chroma=True) 时自动启用；否则 FinRAG 回退到 Retriever。
    """

    def __init__(self, collection_name: str = "quantagent_reports", persist_dir: str | None = None):
        if not _HAS_CHROMA:
            raise RuntimeError("未安装 chromadb，无法启用向量检索。请 `pip install chromadb`。")
        # 关闭联网遥测，避免无网络/沙箱环境下 chromadb 因心跳/上报而阻塞或报 SSL 错
        os.environ["ANONYMIZED_TELEMETRY"] = os.environ.get("ANONYMIZED_TELEMETRY", "False")
        if persist_dir is None:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            persist_dir = os.path.join(root, "data", "chroma_quantagent")
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.coll = self.client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

    def add(self, doc_id: str, text: str):
        # upsert 保证重复 id 幂等更新
        self.coll.upsert(ids=[doc_id], documents=[text])

    def search(self, query: str, k: int = 3) -> List[Dict[str, object]]:
        if self.coll.count() == 0:
            return []
        res = self.coll.query(query_texts=[query], n_results=min(k, self.coll.count()))
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        for i, doc_id in enumerate(ids):
            # chromadb 返回的是 cosine 距离，转成相似度 0-1（1 最相似）
            sim = max(0.0, 1.0 - float(dists[i]))
            out.append({"id": doc_id, "text": docs[i], "score": round(sim, 3)})
        return out


# 内置金融研报/笔记语料（演示用，可由用户持续扩充）
_SEED_CORPUS = [
    {"id": "note_ma", "text": "均线多头排列且站上MA20时趋势偏强，回踩均线是不错的低吸点"},
    {"id": "note_risk", "text": "高波动高回撤标的应严格控制仓位，单标的仓位不超过组合20%"},
    {"id": "note_sentiment", "text": "舆情转正面叠加技术突破常形成戴维斯双击，但需警惕利好兑现"},
    {"id": "note_value", "text": "低PE低PB且ROE稳定属于高确定性价值标的，适合中长期持有"},
]


class MemoryStore:
    """记忆层：episodic（历史决策）+ semantic（用户偏好），JSON 持久化。"""

    def __init__(self, path: str | None = None):
        if path is None:
            # 默认落到 StockSignal 的 data/ 目录
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            path = os.path.join(root, "data", "quantagent_memory.json")
        self.path = path
        self.data: Dict[str, object] = {"episodic": {}, "semantic": {}}
        self._load()

    def _load(self):
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if "episodic" not in self.data:
                    self.data["episodic"] = {}
                if "semantic" not in self.data:
                    self.data["semantic"] = {}
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # episodic
    def save_decision(self, ticker: str, decision: Dict[str, object]):
        ep = self.data["episodic"].setdefault(ticker, [])
        ep.append({"ts": _now(), "verdict": decision.get("verdict"), "target": decision.get("target_price"),
                   "stop": decision.get("stop_price"), "rationale": decision.get("rationale", "")[:200]})
        ep[:] = ep[-10:]  # 仅保留最近 10 条
        self._save()

    def get_recent(self, ticker: str, n: int = 3) -> List[Dict[str, object]]:
        return (self.data["episodic"].get(ticker, []))[-n:]

    # semantic
    def set_preference(self, key: str, value: object):
        self.data["semantic"][key] = value
        self._save()

    def get_preferences(self) -> Dict[str, object]:
        return self.data["semantic"]


def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


class FinRAG:
    """对外统一入口：记忆 + 检索 → 上下文注入。

    use_chroma=True 且 chromadb 可用时，检索层启用 chromadb 向量库（持久化、可大规模扩展）；
    否则回退到内置 TF-IDF 检索器。记忆层（MemoryStore）始终启用。
    """

    def __init__(self, memory_path: str | None = None, use_chroma: bool = True):
        self.memory = MemoryStore(memory_path)
        self.using_chroma = False
        if use_chroma and _HAS_CHROMA:
            try:
                self.retriever = ChromaRetriever()
                # 启动时把内置研报/笔记语料灌入向量库（幂等 upsert）
                for item in _SEED_CORPUS:
                    self.retriever.add(item["id"], item["text"])
                self.using_chroma = True
            except Exception:
                self.retriever = Retriever(_SEED_CORPUS)
        else:
            self.retriever = Retriever(_SEED_CORPUS)

    def index_report(self, ticker: str, text: str):
        """把一次投研报告加入检索语料（TF-IDF 直接加；chromadb 走 upsert）。"""
        self.retriever.add(f"report_{ticker}_{_now()}", text)

    def save_decision(self, ticker: str, decision: Dict[str, object]):
        """把最终决策写入记忆层（episodic memory）。"""
        self.memory.save_decision(ticker, decision)

    def retrieve_context(self, ticker: str, query: str) -> Dict[str, object]:
        past = self.memory.get_recent(ticker, n=3)
        prefs = self.memory.get_preferences()
        notes = self.retriever.search(query, k=3)
        ctx_lines = []
        if past:
            ctx_lines.append("【该标的过往决策】")
            for p in past:
                ctx_lines.append(f"  - {p['ts']}：{p.get('verdict')} 目标{p.get('target')} 止损{p.get('stop')}")
        if prefs:
            ctx_lines.append("【用户偏好】")
            for k, v in prefs.items():
                ctx_lines.append(f"  - {k}: {v}")
        if notes:
            ctx_lines.append("【相关研报/笔记】")
            for n in notes:
                ctx_lines.append(f"  - ({n['score']}) {n['text']}")
        return {
            "context": "\n".join(ctx_lines),
            "memory": {"past_decisions": past, "preferences": prefs},
        }
