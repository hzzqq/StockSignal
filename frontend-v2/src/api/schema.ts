import { z } from 'zod'

/**
 * 响应信封（PLAN.md §1 真扫：`{status, code, message, data}`）
 * 来自 backend/utils/response.py / openapi.py:11-16。
 *
 * 红线：字段逐个校验，禁止 `?? 0` / 默认值兜底。
 * 字段级 schema 仍需逐端点核对（W0 写回结论），所以 data 用 z.unknown() 保留，
 * 具体结构在各自接口处再用专用 schema 解析。
 */
export const EnvelopeResponse = z.object({
  status: z.enum(['ok', 'error']),
  code: z.string().min(1),
  message: z.string(),
  // data 允许任意类型（含 null），但不给默认值——缺字段直接抛错
  data: z.unknown(),
})

export type Envelope = z.infer<typeof EnvelopeResponse>

/** 登录请求体 */
export const LoginRequest = z.object({
  username: z.string().min(1, '用户名不能为空'),
  password: z.string().min(1, '密码不能为空'),
})
export type LoginRequestType = z.infer<typeof LoginRequest>

/**
 * 登录响应 data 结构（兼容真后端 / MSW 双字段名）。
 *
 * 真后端 auth/routes.py::login / refresh 返回 data.token（+ user 对象）；
 * MSW handlers.ts 返回 data.access_token。后端契约被 legacy Streamlit 等消费方
 * 依赖、MSW 由 mock 契约固定，二者都不改，由前端在此归一。
 *
 * 诚实红线：两个 token 字段都缺必须抛错，禁止 `?? ''` / 默认值兜底。
 * transform 归一出必填 string 类型的 access_token，使下游 client.ts / LoginPage
 * 读 access_token 的代码保持零改动（z.infer 得到 string，非 string | undefined）。
 */
export const LoginData = z
  .object({
    access_token: z.string().min(1).optional(),
    token: z.string().min(1).optional(),
    refresh_token: z.string().min(1).optional(),
    token_type: z.string().default('Bearer'),
    expires_in: z.number().int().positive().optional(),
  })
  .transform((d, ctx) => {
    const token = d.access_token ?? d.token
    if (!token) {
      ctx.addIssue({ code: 'custom', message: '登录响应缺少 access_token 或 token' })
      return z.NEVER
    }
    return {
      access_token: token,
      refresh_token: d.refresh_token,
      token_type: d.token_type,
      expires_in: d.expires_in,
    }
  })
export type LoginResult = z.infer<typeof LoginData>

/** 严格解析信封：失败即抛，不兜底 */
export function parseEnvelope(raw: unknown): Envelope {
  return EnvelopeResponse.parse(raw)
}
