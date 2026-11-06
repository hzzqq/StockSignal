import { z } from 'zod'
import { apiFetch } from './client'
import { LoginData, LoginRequest, type LoginResult } from './schema'

/**
 * W1 接契约：按后端 OpenAPI 实跑基线（64 paths / 87 ops，见 frontend-v2/spec/openapi.json）
 * 构建「类型安全 + Zod 运行时校验」的 API 客户端。
 *
 * 设计取舍（诚实标注）：后端当前 spec 的响应体统一引用 EnvelopeResponse
 * （逐端点 data 字段 schema 待补），因此 auto-gen 客户端只能产出 `unknown` 数据，
 * 价值有限；且 openapi-typescript@7 的 peer 要 TS5.x 与本项目锁定的 TS7.0.2 冲突。
 * 故采用**手写 Zod 校验的薄客户端**：路径/方法对齐契约，data 用专用 schema 严格解析，
 * 缺失/类型不符即抛错（禁 `?? 0` 兜底），与 PLAN.md §4.3 红线一致。
 */

/** GET /api/health —— 服务健康探针 */
export const HealthData = z.object({
  service: z.string(),
  status: z.enum(['alive', 'degraded']),
  components: z.object({
    backend: z.string(),
    database: z.string(),
    database_detail: z.string().optional(),
  }),
})
export type HealthData = z.infer<typeof HealthData>

/** 登录：POST /api/auth/login，写入 token 由调用方负责（guards / LoginPage） */
export async function login(username: string, password: string): Promise<LoginResult> {
  const parsed = LoginRequest.parse({ username, password })
  const data = await apiFetch<unknown>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(parsed),
  })
  return LoginData.parse(data) // 抛错即失败，不兜底
}

/** 健康检查 */
export async function getHealth(): Promise<HealthData> {
  const data = await apiFetch<unknown>('/health')
  return HealthData.parse(data)
}

/**
 * 只读数据端点（W1 后端 /api/v2/read/*，代理原 12 页直读本地文件）。
 * 泛型 T 由调用方用专用 Zod schema 解析；此处只负责信封解包 + 路径拼接。
 */
export async function getRead<T = unknown>(source: string): Promise<T> {
  const data = await apiFetch<T>(`/v2/read/${encodeURIComponent(source)}`)
  return data
}
