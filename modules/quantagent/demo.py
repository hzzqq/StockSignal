"""
modules/quantagent/demo.py
--------------------------
QuantAgent 离线冒烟测试（无需网络 / 无需 LLM Key 即可跑通全链路）。

  运行：
  cd /d/project/ks/StockSignal
  python -m modules.quantagent.demo                 # 默认 600519，覆盖全部组件
  python -m modules.quantagent.demo 000001 --engine langgraph --hitl

演示覆盖：
  - 零依赖编排（simple）与真实 LangGraph 编排（langgraph/auto）自动切换
  - 条件路由 + 人工审批（HITL）：触发 interrupt 后自动/手动恢复
  - FinBrowser：真实 browser-use（若已装 + 有 LLM）或 requests/mock 回退
  - FinRAG：chromadb 向量检索（若已装）或 TF-IDF 回退
  - 二次运行召回 FinRAG 历史决策记忆
"""

from __future__ import annotations

import argparse
import os
import sys


def _ensure_path():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)


def _banner(t: str):
    print("\n" + "=" * 64)
    print(t)
    print("=" * 64)


def main():
    _ensure_path()
    from modules.quantagent import HAS_LANGGRAPH, run_research, format_report, BrowserAgent
    from modules.quantagent.rag_module import _HAS_CHROMA

    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="?", default="600519")
    ap.add_argument("--engine", default="auto", choices=["auto", "langgraph", "simple"])
    ap.add_argument("--hitl", action="store_true", help="演示 LangGraph 人工审批（强制复核）")
    args = ap.parse_args()

    ticker = args.ticker
    _banner(f"QuantAgent demo · {ticker} · engine={args.engine} · hitl={args.hitl}")
    print(f"[环境] langgraph={'已安装' if HAS_LANGGRAPH else '未安装(回退simple)'} | "
          f"chromadb={'已安装' if _HAS_CHROMA else '未安装(回退TF-IDF)'}")

    # 1) 主流程
    state = run_research(
        ticker,
        use_browser=True,
        use_rag=True,
        engine=args.engine,
        force_human_review=args.hitl,
        human_approval_enabled=args.hitl,
    )
    print(format_report(state))
    print(f"\n[组件状态] used_browser={state.used_browser} used_rag={state.used_rag} "
          f"used_llm={state.used_llm} approval={state.approval}")

    # 2) FinBrowser 组件单独验证（真实/回退）
    _banner("FinBrowser 组件验证")
    ba = BrowserAgent()
    print(f"FinBrowser 当前模式: {'browser-use 真实' if ba.real else 'requests/mock 回退'}")
    print("网页舆情:", ba.fetch_web_sentiment(ticker))

    # 3) FinRAG 组件单独验证
    _banner("FinRAG 组件验证")
    from modules.quantagent import FinRAG

    fr = FinRAG(use_chroma=True)
    print(f"FinRAG 检索层: {'chromadb 向量库' if fr.using_chroma else 'TF-IDF 兜底'}")
    hits = fr.retriever.search(f"{ticker} 投研决策", k=2)
    for h in hits:
        print(f"  - [{h['score']}] {h['text'][:50]}")

    # 4) 二次运行：召回历史决策记忆
    _banner("二次运行（应召回上次决策记忆）")
    state2 = run_research(ticker, use_browser=True, use_rag=True, engine=args.engine,
                          force_human_review=args.hitl, human_approval_enabled=args.hitl)
    print(format_report(state2))

    _banner("✅ QuantAgent 四件套冒烟测试完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
