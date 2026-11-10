import { describe, it, expect } from 'vitest'
import { LoginData, parseEnvelope, type LoginResult } from '@/api/schema'

/**
 * 登录契约回归：从真实 schema.ts import（不复制粘贴 schema，避免自证）。
 * 覆盖真后端 data.token / MSW data.access_token 双字段名，以及「两字段都缺必抛错」
 * 的诚实红线（禁止 ?? '' / 默认值兜底）。纯本地单测，不依赖网络 / DOM。
 */
describe('LoginData — 双字段名兼容 + 无静默兜底', () => {
  it('真后端形状（完整信封 data.token + user）→ parseEnvelope + LoginData 归一成功', () => {
    const raw = {
      status: 'ok',
      code: 'ok',
      message: 'success',
      data: {
        token: 'real-jwt-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig',
        // 真后端 auth/routes.py::login 返回 User.to_public()（含 is_active 等全字段），
        // 与 PublicUserSchema 严格对齐——此处不复刻残缺对象，避免契约失真。
        user: {
          id: 1,
          username: 'demo',
          role: 'user',
          created_at: '2026-01-01T08:00:00Z',
          is_active: true,
          avatar: null,
          settings: {},
        },
      },
    }
    const env = parseEnvelope(raw)
    const parsed = LoginData.parse(env.data)
    expect(parsed.access_token).toBe('real-jwt-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig')
  })

  it('MSW 形状（data.access_token + refresh/token_type/expires_in）→ 解析成功', () => {
    const parsed = LoginData.parse({
      access_token: 'mock-access-token',
      refresh_token: 'mock-refresh-token',
      token_type: 'Bearer',
      expires_in: 3600,
    })
    expect(parsed.access_token).toBe('mock-access-token')
    expect(parsed.refresh_token).toBe('mock-refresh-token')
    expect(parsed.token_type).toBe('Bearer')
    expect(parsed.expires_in).toBe(3600)
  })

  it('两个 token 字段都缺 → 必须抛错（无静默兜底）', () => {
    expect(() => LoginData.parse({})).toThrow()
    // 即便 user 合法，缺 token 也必须抛错（诚实红线：禁止 ?? '' 兜底）
    expect(() =>
      LoginData.parse({
        user: { id: 1, username: 'demo', role: 'user', created_at: '2026-01-01T08:00:00Z', is_active: true, avatar: null, settings: {} },
      }),
    ).toThrow()
    expect(() => LoginData.parse({ refresh_token: 'only-refresh' })).toThrow()
  })

  it('空串 token 也应被拒（z.string().min(1) 不放行）', () => {
    expect(() => LoginData.parse({ access_token: '' })).toThrow()
    expect(() => LoginData.parse({ token: '' })).toThrow()
  })

  it('归一后 access_token 类型为 string（编译期保证，非 string | undefined）', () => {
    const parsed = LoginData.parse({ token: 'jwt' })
    // 若 access_token 被推断为 string | undefined，下一行 tsc 即报错
    const token: string = parsed.access_token
    expect(token).toBe('jwt')
    // LoginResult 类型层同样保证为 string，供 client.ts / LoginPage 零改动读取
    const typed: LoginResult = parsed
    const token2: string = typed.access_token
    expect(token2).toBe('jwt')
  })
})
