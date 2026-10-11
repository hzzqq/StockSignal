"""T-267：Flask vs FastAPI 同构最小 App 双场景压测（框架本底开销对照）。

公平性设计：两框架各自实现**同构最小 App**（health 轻端点 + /io 20ms 等待端点），
排除业务差异，测「框架层」本底；各用框架惯用法写 IO 端点：
    Flask   /io  -> 同步视图 time.sleep(0.02)（threaded 每请求一线程）
    FastAPI /io  -> async def + await asyncio.sleep(0.02)（事件循环并发）
两场景：
    A. /health —— 纯 CPU 轻端点（同步，对 FastAPI 最不利的口径）
    B. /io    —— 外部等待 20ms（IO 密集，FastAPI 异步主场）
另附存量生产 app.py 的 health 实测（backend FastAPI 切片同口径）供参考。

诚实口径：双方均为 dev server（werkzeug threaded / uvicorn 单进程），
测框架层开销，不代表生产多进程部署差距。
用法：uv run python scripts/bench_api_compare.py
产出：docs/bench_api_compare.json
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

FLASK_PORT, FASTAPI_PORT = 5053, 5052
N_REQUESTS = 3000
CONCURRENCY = 50
IO_SLEEP = 0.02

MINIMAL_FLASK = r'''
from flask import Flask, jsonify
import time
app = Flask(__name__)
@app.get("/health")
def health():
    return jsonify(status="ok")
@app.get("/io")
def io_wait():
    time.sleep(__IO__)
    return jsonify(status="ok")
app.run(host="127.0.0.1", port=__PORT__, threaded=True, debug=False)
'''

MINIMAL_FASTAPI = r'''
import asyncio
from fastapi import FastAPI
app = FastAPI()
@app.get("/health")
async def health():
    return {"status": "ok"}
@app.get("/io")
async def io_wait():
    await asyncio.sleep(__IO__)
    return {"status": "ok"}
'''


def _spawn_inline(code: str, port: int, framework: str) -> subprocess.Popen:
    """内联最小 App 落临时文件后用项目 .venv 解释器启动（同解释器同库，公平）。"""
    tmp = Path(os.environ["TEMP"]) / f"bench_min_{framework}_{port}.py"
    tmp.write_text(code.replace("__IO__", str(IO_SLEEP)).replace("__PORT__", str(port)),
                   encoding="utf-8")
    if framework == "flask":
        cmd = [sys.executable, str(tmp)]
        env_extra = {}
    else:
        cmd = [sys.executable, "-m", "uvicorn", f"bench_min_{framework}_{port}:app",
               "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
        env_extra = {"PYTHONPATH": str(tmp.parent)}
    env = {**os.environ, **env_extra}
    return subprocess.Popen(cmd, cwd=str(tmp.parent), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_ready(url: str, timeout: float = 40.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return True
        except Exception:
            time.sleep(0.3)
    return False


async def _bench(url: str, n: int = N_REQUESTS, conc: int = CONCURRENCY,
                 sequential: bool = False) -> dict:
    """sequential=True：顺序请求（无并发调度噪声，测单请求处理开销）；
    sequential=False：并发参考口径（同机客户端调度噪声大，仅参考）。"""
    latencies: list[float] = []
    errors = 0

    async def worker(client: httpx.AsyncClient, sem: asyncio.Semaphore):
        nonlocal errors
        async with sem:
            t0 = time.perf_counter()
            try:
                if (await client.get(url)).status_code != 200:
                    errors += 1
            except Exception:
                errors += 1
            latencies.append(time.perf_counter() - t0)

    t0 = time.perf_counter()
    if sequential:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(n):
                t1 = time.perf_counter()
                try:
                    if (await client.get(url)).status_code != 200:
                        errors += 1
                except Exception:
                    errors += 1
                latencies.append(time.perf_counter() - t1)
        wall = time.perf_counter() - t0
    else:
        sem = asyncio.Semaphore(conc)
        async with httpx.AsyncClient(timeout=30.0) as client:
            await asyncio.gather(*[worker(client, sem) for _ in range(n)])
        wall = time.perf_counter() - t0

    lat_ms = sorted(x * 1000 for x in latencies)

    def pct(p: float) -> float:
        return round(lat_ms[min(int(len(lat_ms) * p), len(lat_ms) - 1)], 2)

    return {"requests": n, "concurrency": 1 if sequential else conc, "errors": errors,
            "wall_sec": round(wall, 2), "rps": round(n / wall, 1),
            "p50_ms": pct(0.50), "p95_ms": pct(0.95), "p99_ms": pct(0.99),
            "mean_ms": round(statistics.fmean(lat_ms), 2)}


def main() -> int:
    fproc = _spawn_inline(MINIMAL_FLASK, FLASK_PORT, "flask")
    faproc = _spawn_inline(MINIMAL_FASTAPI, FASTAPI_PORT, "fastapi")
    try:
        ok1 = _wait_ready(f"http://127.0.0.1:{FLASK_PORT}/health")
        ok2 = _wait_ready(f"http://127.0.0.1:{FASTAPI_PORT}/health")
        if not (ok1 and ok2):
            print(f"服务未就绪: flask={ok1} fastapi={ok2}")
            return 1

        r = {
            "io_sleep_ms": int(IO_SLEEP * 1000),
            "note": "同构最小 App 双场景；双方 dev server（werkzeug threaded / uvicorn 单进程），"
                    "主口径=顺序请求（无客户端并发调度噪声，测框架单请求开销），并发口径仅参考",
            "health_cpu_light": {
                "flask_sequential": asyncio.run(_bench(f"http://127.0.0.1:{FLASK_PORT}/health",
                                                       n=500, sequential=True)),
                "fastapi_sequential": asyncio.run(_bench(f"http://127.0.0.1:{FASTAPI_PORT}/health",
                                                         n=500, sequential=True)),
                "flask_conc_ref": asyncio.run(_bench(f"http://127.0.0.1:{FLASK_PORT}/health",
                                                     n=1000, conc=20)),
                "fastapi_conc_ref": asyncio.run(_bench(f"http://127.0.0.1:{FASTAPI_PORT}/health",
                                                       n=1000, conc=20)),
            },
            "io_wait_20ms": {
                "flask_sequential": asyncio.run(_bench(f"http://127.0.0.1:{FLASK_PORT}/io",
                                                       n=500, sequential=True)),
                "fastapi_sequential": asyncio.run(_bench(f"http://127.0.0.1:{FASTAPI_PORT}/io",
                                                         n=500, sequential=True)),
                "flask_conc_ref": asyncio.run(_bench(f"http://127.0.0.1:{FLASK_PORT}/io",
                                                     n=1000, conc=20)),
                "fastapi_conc_ref": asyncio.run(_bench(f"http://127.0.0.1:{FASTAPI_PORT}/io",
                                                       n=1000, conc=20)),
            },
        }
        h, io = r["health_cpu_light"], r["io_wait_20ms"]
        r["conclusion"] = {
            "health_seq_mean_ratio_fastapi_over_flask": round(
                h["fastapi_sequential"]["mean_ms"] / h["flask_sequential"]["mean_ms"], 2),
            "io_seq_mean_ratio_fastapi_over_flask": round(
                io["fastapi_sequential"]["mean_ms"] / io["flask_sequential"]["mean_ms"], 2),
        }
        out = ROOT / "docs" / "bench_api_compare.json"
        out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print("报告:", out)
        return 0
    finally:
        for p in (fproc, faproc):
            p.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
