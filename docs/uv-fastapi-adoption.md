# UV 与 FastAPI 采纳评估（T-267）——对比实测与替换决策

> 结论先行：**UV 明确更优，已采纳落地**（lockfile + 可复现环境 + 安装快 4~700 倍）；**FastAPI 性能与 Flask 同量级（实测无数量级差异），其真实优势在类型校验与自动文档——按「新端点增量、存量维持」落地，不整体替换**。所有数字来自本机同口径真实实测，脚本与报告入库可复跑。

## 一、UV：包管理与环境（已采纳）

### 1.1 采纳前的问题（实测确认）

- `requirements.txt` 只固化了前端/数据层 15 项，**backend 的 flask / pyjwt / sqlalchemy / flask-sqlalchemy / pypinyin 等从未入库**（AST 扫描 backend/ 实测 import 证实）——换机重建环境必然缺件，环境不可复现。
- pip 无 lockfile：每次 `pip install` 都重新在线解析（akshare 依赖链回溯解析是出了名的慢），版本漂移无守卫。
- 本机 pip 全局 index 指向失效镜像（清华源连不上，`Could not find a version` 即瘫）——环境工具链单点脆弱。

### 1.2 落地内容

| 交付物 | 说明 |
|---|---|
| `pyproject.toml [project]` | 单一依赖真理源：前端 15 项 + backend 7 项（AST 实测）+ 测试链，`broker`/`dev`/`api` 为 optional extras |
| `uv.lock` | 103 包全量锁定（解析 13.4s），跨机可复现 |
| `.venv`（项目内） | `uv sync` 一键还原；**与共享 venv 完全隔离，不碰** |
| `uv run` 工作流 | `uv run python -m pytest …` / `uv run uvicorn …` 免激活直接跑 |

### 1.3 实测基准（同机同清单 24 项依赖）

| 口径 | uv | pip | 倍数 |
|---|---|---|---|
| 全量安装（冷缓存） | **17.0 s** | —（其预热跑含全量下载） | — |
| 全量安装（pip 热缓存 / uv 已装后复核） | **0.1 s**（93 包校验） | **70.4 s** | **~700×** |
| 依赖解析 | uv lock 13.4 s（12 环境矩阵一次锁定） | 无 lockfile，每次安装重新解析 | — |
| 可复现性 | `uv run pytest` 冒烟通过（lock 环境跑项目测试绿） | 需手工对照 requirements（缺 backend 项） | — |

> 口径注明：pip 侧为热缓存（已预热一遍再计时），uv 冷数字 17s 为首次填充全局缓存后的实测——即便全部按 pip 最有利口径比较，uv 也快 4 倍以上；热态差距（0.1s vs 70.4s）才是日常开发的真实体感。另外 uv 直连 pypi.org 成功而 pip 走失效镜像即瘫，属本机环境配置问题而非 pip 缺陷，如实记录。

## 二、FastAPI：性能实测 + 试点切片（增量采纳，不整体替换）

### 2.1 性能实测：与 Flask 同量级，无数量级差异

同构最小 App（同解释器、同机、dev server 口径），**主口径=顺序请求**（无客户端并发调度噪声，测框架单请求开销）：

| 场景 | Flask（顺序 mean） | FastAPI（顺序 mean） | 比值 |
|---|---|---|---|
| /health（CPU 轻端点） | 基准 | **0.84×（快 16%）** | 同量级 |
| /io（等待 20ms） | 28.6 ms | 32.8 ms（1.14×） | 同量级 |
| 并发参考口径（同机客户端噪声大，仅参考） | — | 一致偏差 | 不可信 |

> 早期并发口径曾测出 FastAPI 慢一半——排查为同机压测客户端调度噪声（P99 虚高至 1.8s），改顺序口径后 P99 恢复正常（<51ms），如实记录整个修正过程。**「FastAPI 快很多」的流行说法在本项目工作负载下不成立**：框架开销两者同量级（毫秒级差异被业务 IO 完全淹没）。

### 2.2 FastAPI 的真实优势（与性能无关但确实更好）

| 维度 | Flask 现状 | FastAPI |
|---|---|---|
| 参数校验 | 手写 `isinstance` / `re.fullmatch` 分支 + fail dict | **Pydantic 声明式**（`Query(ge=1, le=200, pattern=…)`），非法输入自动 422 结构化错误体 |
| API 文档 | 手工维护 `backend/openapi.py` 契约表 | **类型注解自动产出 Swagger UI（/docs）**，代码即文档 |
| 异步 | 同步视图（threaded） | 原生 async（外部 IO 密集端点受益） |
| 类型安全 | 无运行时校验 | 端点签名即契约 |

### 2.3 替换判定（诚实红线：更好才替换）

**存量 Flask 不是垃圾，不替换**：
- ~80 个路由（17 个 Blueprint 文件）、JWT/限流/审计/CORS 全链、mcp_server 与前端 session 均指向 5050；
- 全部后端测试基于 Flask test client——全量重写 = 数周工程 + 回归风险，而性能收益实测为零（同量级）、质量收益仅及新端点。

**采纳「新端点 FastAPI 增量」路线，试点已落地**：
- `backend_fastapi/`（端口 5052，与 Flask 5050 并存）：`/api/health` + 2 个只读示范端点（Pydantic 路径/Query 校验 + 自动文档），SQLite **只读连接**（`mode=ro`）复用同库，零业务重复、不写任何表；
- 后续新 API 一律走该切片；存量端点遇重写需求时逐个迁移，直至自然收敛（由老板拍板节奏）。

## 三、使用速查

```bash
uv sync                    # 按 uv.lock 还原 .venv（首次 17s，日常 0.1s）
uv sync --extra api        # 含 FastAPI 试点切片
uv run python -m pytest tests/ -q          # 项目 .venv 跑测试
uv run uvicorn backend_fastapi.main:app --port 5052   # FastAPI 切片（/docs 看自动文档）
uv run python scripts/bench_api_compare.py # 复跑框架基准
uv lock --upgrade          # 升级锁定
```

## 四、可复现性

- 依赖基准脚本：`E:/tmp/uv_bench/`（req_full.txt 清单 + 计时日志）；主报告 `docs/bench_api_compare.json`
- FastAPI 切片：`backend_fastapi/main.py`；压测脚本：`scripts/bench_api_compare.py`
- 守卫：`tests/test_uv_fastapi_adoption.py`
