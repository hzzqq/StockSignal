# StockSignal 双后端过渡策略（P1-2 决策记录）

> 依据：母本《KS_改善执行提示词_交付版》P1-2；实证：T-267/268 FastAPI 试点切片（`backend_fastapi/main.py`）。
> 日期：2026-10-30 · 起草：Trae 空间 · 状态：**已冻结（决策规则，改动需老板拍板）**

---

## 1. 现状（2026-10-30 实测）

| 服务 | 入口 | 端口 | 规模 | 角色 |
|------|------|------|------|------|
| Flask 生产后端 | `backend/app.py` | **5050** | ~80 路由，JWT/CORS/限流/审计齐全 | 承载全部存量业务，**生产** |
| FastAPI 试点切片 | `backend_fastapi/main.py` | **5052** | 9 端点（health/demo×2/星辰 AI×6） | 增量演进示范，ASGI + Pydantic + 自动 OpenAPI |

- 两服务**共用同一个 SQLite 库**（`STOCKSIGNAL_API_DB` 同源路径），FastAPI 侧所有查询 **SELECT-only 只读**（`mode=ro` URI），零业务逻辑重复，试点不写任何表。
- 端口布局：8501（Streamlit）/ 5050（Flask）/ 5052（FastAPI）错开，**可同时启动**。
- FastAPI 侧 `/docs`（Swagger UI）由类型注解自动产出，替代 Flask 侧手工维护的 `backend/openapi.py` 契约表。

## 2. 决策（冻结）

1. **存量 Flask 路由维持生产不动**：~80 路由全量重写成本 >> 收益，不做无收益迁移、不设全量迁移时间表。
2. **一切新端点走 `backend_fastapi`（5052）**：增量演进；Pydantic 声明式校验 + 自动文档是默认收益。
3. **只读边界沿用试点约定**：FastAPI 侧查询保持 SELECT-only；确需写操作的新端点，先在 `team/DECISIONS.md` 备案，并复用 Flask 层既有业务函数，禁止两套实现漂移。

## 3. 迁移触发条件（满足其一，优先在 FastAPI 实现或重写）

- 某功能**需要重写**（技术债过高、改不动、或需求已变）；
- 同一业务域**新增端点 > 3 个**；
- 需要**异步/流式/高并发**特性且 Flask 改造成本过高。

## 4. 终点判定

- 不强制全量迁移。当 FastAPI 覆盖某业务域全部端点且稳定运行一个观察期后，由老板拍板该域 Flask 路由是否下线。
- 下线任何 Flask 路由前必须同时满足：该域 100% FastAPI 等价实现 + 冒烟守卫全绿 + `team/DECISIONS.md` 备案。

## 5. 验收对照（母本 P1-2）

- [x] 本文件存在并记录决策与迁移触发条件
- [x] 两服务入口可同时启动（端口错开实测；`backend/app.py` 与 `backend_fastapi/main.py` py_compile 双通过；5050 为老板常驻服务，不做重启验证）
- [ ] `pytest tests/ -q` 全绿 —— 归 T-353 T6 终验统一执行
