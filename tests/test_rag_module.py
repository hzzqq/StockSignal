"""
tests/test_rag_module.py
=======================
FinRAG 轻量检索层（modules.quantagent.rag_module）纯逻辑测试。

覆盖：分词（None/中文/英文）、TF-IDF 检索器的空语料/相关召回/无重叠兜底/k 截断、
文档缺 text 键不再 KeyError（回归守护）、本地 embedding 维度与归一化、空文本。
不涉及 chromadb（可选依赖）。
"""
import math

import pytest

import modules.quantagent.rag_module as rag


def test_tokenize_none_and_empty():
    assert rag._tokenize(None) == []
    assert rag._tokenize("") == []
    assert rag._tokenize("!!!") == []


def test_tokenize_chinese_and_english():
    toks = rag._tokenize("Hello 世界 123")
    assert "hello" in toks
    # 中文按字切分（模块设计：逐字 token）
    assert "世" in toks and "界" in toks
    assert "123" in toks


def test_retriever_empty_corpus_returns_empty():
    r = rag.Retriever([])
    assert r.search("anything") == []


def test_retriever_search_returns_relevant():
    r = rag.Retriever([
        {"id": "a", "text": "均线多头排列站上 MA20 趋势偏强"},
        {"id": "b", "text": "控制仓位单标的不超过组合百分之二十"},
    ])
    res = r.search("均线 趋势", k=1)
    assert len(res) == 1
    assert res[0]["id"] == "a"
    assert res[0]["score"] > 0


def test_retriever_search_no_overlap_returns_fallback():
    r = rag.Retriever([
        {"id": "a", "text": "半导体设备国产替代"},
        {"id": "b", "text": "消费白马估值修复"},
    ])
    # 查询与语料无词重叠 → 兜底返回前 k 条（score=0）
    res = r.search("zzzzz", k=2)
    assert len(res) == 2
    assert all(x["score"] == 0.0 for x in res)


def test_retriever_search_k_limits_count():
    r = rag.Retriever([
        {"id": str(i), "text": f"document number {i} about stocks"}
        for i in range(10)
    ])
    res = r.search("stocks document", k=3)
    assert len(res) <= 3


def test_retriever_search_missing_text_key_no_crash():
    """回归：文档缺 text 键时 search 不应 KeyError（_build 用 .get 读取，
    search 此前却用硬键访问，文献/记忆缺 text 会让检索整段崩溃）。"""
    r = rag.Retriever([{"id": "x"}])  # 无 text 键
    res = r.search("anything", k=2)
    # 空 text 文档被纳入且 text 为空串，不崩溃
    assert any(d["id"] == "x" for d in res)
    assert all("text" in d for d in res)


def test_local_embedding_dim_and_normalized():
    ef = rag.LocalEmbeddingFunction(dim=16)
    vecs = ef(["均线 多头 MA20 趋势"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 16
    norm = math.sqrt(sum(v * v for v in vecs[0]))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_local_embedding_empty_text_is_zero_vector():
    ef = rag.LocalEmbeddingFunction(dim=8)
    vecs = ef([""])
    assert len(vecs) == 1
    assert vecs[0] == [0.0] * 8
