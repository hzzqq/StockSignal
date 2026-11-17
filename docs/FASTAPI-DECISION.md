# FastAPI 迁移决策报告（2026-11-17）

## 结论先行

**不做全量迁移。维持 Flask 生产 + FastAPI 增量切片双轨。**

老板的技术栈铁律是「收益 > 成本即换」。本次实测取证的成本远超收益，
全量重写属于「改动太大但收益不足」——按同一铁律，**不换**。
这不是因循守旧：项目自己早在 T-267 就做过 FastAPI 试点并得出同样结论
（见 `backend_fastapi/main.py` 头部「全量重写成本 >> 收益，维持生产」）。

## 一、实测成本面（2026-11-17）

| 项目 | 实测值 | 取证方式 |
|---|---|---|
| Flask 路由总数 | **159**（含 158 业务 + 框架） | `from backend.app import app; len(list(app.url_map.iter_rules()))` |
| Blueprint 路由装饰器 `@bp.*` | **152** 处 | grep backend/ `*.py` |
| `@jwt_required` 鉴权装饰器 | **142** 处 | 同上 |
| `g.current_user` 使用 | **69** 处 | 同上 |
| `before_request/after_request/errorhandler` | 0（好事：无宿主钩子依赖） | 同上 |
| 后端测试面 | ~600 用例 | backend/tests/ |
| 环境 | fastapi 0.139.2 / uvicorn 0.49.0 已装 | `import` 实测 |

**换算**：142 处鉴权装饰器 + 69 处 `g.current_user` = **211 处必须手工改写成
FastAPI `Depends` + 请求上下文**；再叠加 ~600 个依赖 Flask `test_client` 的用例改造。
按保守估计，这是**数周到数月的全量回归工程**，且迁移期两套后端并存会放大鉴权不一致风险。

## 二、收益面（为什么不足以覆盖成本）

| FastAPI 收益 | 本项目现状是否已具备 |
|---|---|
| 类型校验 / Pydantic | ✅ `frontend-v2` 已有 Zod schema 校验；后端手写校验在 158 端点上稳定跑了数月 |
| 自动 OpenAPI | ✅ Flask 侧已有手写 `openapi.py` 契约表 + CI 守卫（端点数一致性 158） |
| 异步 ASGI | ⚠️ 本项目瓶颈在**数据源 IO**（已有共享有界线程池 + fetch_many 并发），不在 Web 框架 |
| 性能 | ⚠️ 单机个人投研工具，Flask dev server 足用；生产化收益仅在多用户高并发场景才显著 |

**结论**：收益主要是「架构现代性」，而成本是「211 处鉴权改造 + 600 用例回归 + 迁移期双轨风险」。
用项目自己的判据衡量，明显 **收益 < 成本**。

## 三、已落地的增量路线（不是空谈）

项目已有 `backend_fastapi/` 试点（T-267/268），运行方式：
```bash
uvicorn backend_fastapi.main:app --port 5052   # 或 python -m backend_fastapi.main
# Swagger 文档：http://127.0.0.1:5052/docs
```
试点已包含 health + 只读数据 + 星辰 AI 服务层（知识库/意图/对话），
与 Flask **共用同一个 SQLite 库**（只读 SELECT），零业务逻辑重复。

### 增量规则（写进团队约定）

1. **新端点一律 FastAPI**：在 `backend_fastapi/` 加路由，享受 Pydantic 校验 + 自动 OpenAPI。
2. **存量 158 端点保持 Flask**：除非某端点出现真实性能/类型瓶颈，才单点迁移（逐点、可回滚）。
3. **禁止双份业务逻辑**：FastAPI 侧只做薄适配 + 复用 `modules/` 逻辑层（与 Flask 共用同一真理源）。
4. **不碰鉴权双轨**：JWT HS256 仍在 Flask 侧统一签发；FastAPI 侧只读场景用共享校验，写场景暂不开放。

## 四、什么时候重新评估（触发条件，别无限挂起）

出现任一条件立即重开评估：
- 生产部署要求 **多用户高并发**（>100 并发持续）且 Flask 线程池成瓶颈；
- 需要 **SSE / WebSocket 流式响应**（AI Copilot 场景）——FastAPI 原生支持，Flask 需扩展；
- 团队规模扩大到 **3+ 人并行开发后端**，类型契约收益显著。

## 五、本次交付

- 本报告（`docs/FASTAPI-DECISION.md`）——保留决策依据，供后续复核，避免重复争论。
- 代码零改动——不为"看起来在推进"而硬迁。
