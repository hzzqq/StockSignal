"""
tests/test_uv_fastapi_adoption.py
=================================
T-267 UV + FastAPI 采纳守卫。

契约：
1. pyproject [project] 依赖真理源：前端与 backend 关键依赖必须入库
   （backend 的 flask/pyjwt/sqlalchemy 此前从未固化——AST 实测缺口）。
2. uv.lock 存在且覆盖 flask（lockfile 是可复现环境的锚）。
3. FastAPI 试点切片：backend_fastapi/main.py 必须携带只读边界（mode=ro）、
   health 端点、Pydantic Query 校验声明；绝不引入写库语句。
4. docs/bench_api_compare.json 基准报告存在且结论字段完整（防数据漂移）。

mutation：删 [project] flask 行 / 切片引入 UPDATE 语句 → 对应用例变红。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
UVLOCK = ROOT / "uv.lock"
FA_MAIN = ROOT / "backend_fastapi" / "main.py"
BENCH = ROOT / "docs" / "bench_api_compare.json"


def test_pyproject_carries_backend_deps():
    """契约1：依赖真理源必须同时覆盖前端与 backend（含此前缺失的 flask 系）。"""
    src = PYPROJECT.read_text(encoding="utf-8")
    assert "[project]" in src
    for dep in ("flask>=3.0.0", "pyjwt>=2.8.0", "sqlalchemy>=2.0.0",
                "flask-sqlalchemy>=3.1.0", "akshare>=1.12.0", "streamlit>=1.35.0",
                "httpx>=0.27.0"):
        assert dep in src, f"pyproject 缺依赖: {dep}"


def test_uv_lock_exists_and_pins_flask():
    """契约2：uv.lock 存在且锁定 flask（可复现环境锚）。"""
    assert UVLOCK.exists(), "uv.lock 缺失——环境不可复现"
    lock = UVLOCK.read_text(encoding="utf-8")
    assert 'name = "flask"' in lock, "uv.lock 未锁定 flask"
    assert 'name = "fastapi"' in lock, "uv.lock 未锁定 fastapi（api extra）"


def test_fastapi_slice_readonly_boundary():
    """契约3：试点切片必须保持只读边界 + 校验声明，不得引入写库语句。"""
    src = FA_MAIN.read_text(encoding="utf-8")
    assert "mode=ro" in src, "只读连接边界缺失（试点红线：绝不写库）"
    assert '"/api/health"' in src, "health 端点缺失（基准对照锚）"
    assert "Query(" in src, "Pydantic Query 校验声明缺失"
    bad = ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP TABLE", "ALTER TABLE")
    upper = src.upper()
    for kw in bad:
        assert kw not in upper, f"试点切片出现写库语句: {kw}"


def test_bench_report_exists_and_complete():
    """契约4：基准报告存在、双场景 + 结论比值字段完整（防止数据漂移/误读）。"""
    assert BENCH.exists(), "docs/bench_api_compare.json 缺失"
    r = json.loads(BENCH.read_text(encoding="utf-8"))
    for scene in ("health_cpu_light", "io_wait_20ms"):
        assert scene in r, f"基准缺场景: {scene}"
        assert "flask_sequential" in r[scene] and "fastapi_sequential" in r[scene]
        assert r[scene]["flask_sequential"]["errors"] == 0
    assert "conclusion" in r and "health_seq_mean_ratio_fastapi_over_flask" in r["conclusion"]
    # 诚实口径护栏：比值应在同量级（0.3~3.0）内——超出说明口径被污染，须复核
    for k, v in r["conclusion"].items():
        assert 0.3 <= v <= 3.0, f"{k}={v} 超出同量级范围，基准口径可能被污染"
