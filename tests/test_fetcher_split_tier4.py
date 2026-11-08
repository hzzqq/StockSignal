"""T-247 结构性重构守卫：ReferenceMixin 抽出 + 进程内 TTL 缓存收敛 ProcTTLCache。

锁死三条不变量，防止拆分回潮：
1. ``ReferenceMixin`` 真身定义在 fetcher_base.py，且 BaseFetcher/StockFetcher 经 MRO 继承它；
2. ``ProcTTLCache`` 真身定义在 fetcher_core/__init__.py 并 re-export 到 fetcher_base.py；
3. ``StockFetcher._fund_cache`` / ``_biz_cache`` 必须是 ProcTTLCache 实例（不再是裸 dict），
   旧 ``self._proc_cache_get/_set`` 调用点已迁移到 ``.get/.set`` 对象接口（零行为变化）。
"""
import ast
import pathlib
import time

from modules import fetcher_core
from modules.fetcher import StockFetcher
from modules.fetcher_base import ReferenceMixin

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT / "modules"
FB = BASE / "fetcher_base.py"
FC = BASE / "fetcher_core" / "__init__.py"
FF = BASE / "fetcher_fundamental.py"


# ── 1. ReferenceMixin 抽出且不变量 ──
def test_referencemixin_defined_in_fetcher_base():
    tree = ast.parse(FB.read_text(encoding="utf-8"))
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ReferenceMixin"]
    assert len(classes) == 1, "ReferenceMixin 应且仅在 fetcher_base.py 定义一次"
    assert "ProcTTLCache" not in {n.name for n in ast.walk(tree)
                                  if isinstance(n, ast.ClassDef)}, \
        "ReferenceMixin 与 ProcTTLCache 不应同仓（ProcTTLCache 真身在 fetcher_core）"


def test_referencemixin_in_stockfetcher_mro():
    assert ReferenceMixin in StockFetcher.__mro__, "StockFetcher 必须经 MRO 继承 ReferenceMixin"
    # 参考方法仍可达（行为零变化）：_pinyin_initials_cache 等类属性随 mixin 继承
    assert hasattr(StockFetcher, "_pinyin_initials_cache")
    assert hasattr(StockFetcher, "_INDEX_SINA_PREFIX")
    assert hasattr(StockFetcher, "_get_sina_prefix")


# ── 2. ProcTTLCache 真身与 re-export ──
def test_procttlcache_defined_in_fetcher_core():
    src = FC.read_text(encoding="utf-8")
    assert "class ProcTTLCache" in src, "ProcTTLCache 真身必须在 fetcher_core/__init__.py"
    # re-export 链路：fetcher_base 导入并绑定为类属性来源
    fbsrc = FB.read_text(encoding="utf-8")
    assert "ProcTTLCache," in fbsrc, "fetcher_base 必须从 fetcher_core re-export ProcTTLCache"


def test_procttlcache_reached_from_fetcher_base_namespace():
    # 经 fetcher_base 命名空间可见（与 tier11 同范式）
    import modules.fetcher_base as fb_mod
    assert getattr(fb_mod, "ProcTTLCache", None) is fetcher_core.ProcTTLCache


def test_procttlcache_ttl_semantics():
    """语义等价于旧 _proc_cache_get/_set（基于 time.monotonic），无 sleep 验证过期。"""
    c = fetcher_core.ProcTTLCache()
    assert c.get("k", ttl_seconds=10) is None          # 空缓存 MISS
    c.set("k", "v")
    assert c.get("k", ttl_seconds=10) == "v"           # 未过期命中
    # 人工回拨内部时间戳 → 过期清除
    c._store["k"] = (time.monotonic() - 100, "old")
    assert c.get("k", ttl_seconds=10) is None          # 过期返回 None
    assert "k" not in c._store                         # 过期即清除（与旧行为一致）


# ── 3. 缓存容器实例化为 ProcTTLCache + 调用点迁移 ──
def test_fund_biz_cache_are_procttl_instances():
    assert isinstance(StockFetcher._fund_cache, fetcher_core.ProcTTLCache), \
        "_fund_cache 必须是 ProcTTLCache 实例，而非裸 dict"
    assert isinstance(StockFetcher._biz_cache, fetcher_core.ProcTTLCache), \
        "_biz_cache 必须是 ProcTTLCache 实例，而非裸 dict"


def test_fundamental_call_sites_use_object_api():
    """AST 守卫：fetcher_fundamental.py 的 4 处调用已迁移到 .get/.set，无残留 self._proc_cache_get/set。"""
    src = FF.read_text(encoding="utf-8")
    assert "self._proc_cache_get(" not in src, "残留 self._proc_cache_get 调用（应迁移为 _xxx_cache.get）"
    assert "self._proc_cache_set(" not in src, "残留 self._proc_cache_set 调用（应迁移为 _xxx_cache.set）"
    # 新接口确实就位（4 处：fund get/set、biz get/set）
    assert src.count("_fund_cache.get(code, _ttl)") == 1
    assert src.count("_fund_cache.set(code, res)") == 1
    assert src.count("_biz_cache.get(code, _ttl)") == 1
    assert src.count("_biz_cache.set(code, biz)") == 1


def test_fundamental_cache_roundtrip_via_stockfetcher():
    """集成级：经 StockFetcher 的 ProcTTLCache 实例做 set/get，证明调用点拿到的是同一对象实例。"""
    cache = StockFetcher._fund_cache
    cache.set("T247_PROBE", {"name": "probe"})
    got = cache.get("T247_PROBE", ttl_seconds=10)
    assert got == {"name": "probe"}
    # 清理探针键，避免污染后续用例
    cache._store.pop("T247_PROBE", None)
