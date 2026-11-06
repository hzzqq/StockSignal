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
  code: z.number().int(),
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
 * 登录响应 data 结构。
 * 字段以本仓后端约定为准；W1 接入时会拿 /auth/login 实跑核对并收紧。
 * refresh_token / expires_in 为 optional（后端可能不返回）。
 */
export const LoginData = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1).optional(),
  token_type: z.string().default('Bearer'),
  expires_in: z.number().int().positive().optional(),
})
export type LoginResult = z.infer<typeof LoginData>

/** 严格解析信封：失败即抛，不兜底 */
export function parseEnvelope(raw: unknown): Envelope {
  return EnvelopeResponse.parse(raw)
}
