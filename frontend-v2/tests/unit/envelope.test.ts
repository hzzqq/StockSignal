import { describe, it, expect } from 'vitest'
import { EnvelopeResponse, LoginData, parseEnvelope } from '@/api/schema'

describe('EnvelopeResponse — 严格校验，缺字段即抛错（禁止 ?? 0 兜底）', () => {
  it('解析合法信封', () => {
    const ok = EnvelopeResponse.parse({
      status: 'ok',
      code: 'ok',
      message: 'success',
      data: { a: 1 },
    })
    expect(ok.status).toBe('ok')
    expect(ok.data).toEqual({ a: 1 })
  })

  it('真后端形状（code 为业务码字符串）解析成功', () => {
    const env = parseEnvelope({
      status: 'ok',
      code: 'ok',
      message: 'success',
      data: { service: 'stock-signal' },
    })
    expect(env.code).toBe('ok')
  })

  it('缺字段即抛错', () => {
    expect(() => EnvelopeResponse.parse({ status: 'ok', code: 'ok' })).toThrow()
    expect(() => EnvelopeResponse.parse({ status: 'ok', message: 'x', data: null })).toThrow()
  })

  it('code 非法类型（数字）即抛错', () => {
    expect(() =>
      EnvelopeResponse.parse({ status: 'ok', code: 123, message: 'x', data: null }),
    ).toThrow()
  })

  it('status 非法枚举即抛错', () => {
    expect(() =>
      EnvelopeResponse.parse({ status: 'OK', code: 'ok', message: 'x', data: null }),
    ).toThrow()
  })

  it('parseEnvelope 与 EnvelopeResponse.parse 一致', () => {
    // 正向：code 为合法业务码字符串（真后端 _ok/_fail_payload 的 code 均为字符串）
    const raw = { status: 'error', code: 'unauthorized', message: 'unauthorized', data: null }
    expect(parseEnvelope(raw)).toEqual(raw)
    // code 类型非法（数字 401）即抛错：严格 string，不放宽为 union
    expect(() => parseEnvelope({ status: 'error', code: 401, message: 'x', data: null })).toThrow()
  })
})

describe('LoginData — 登录响应结构校验', () => {
  it('解析合法登录数据', () => {
    const d = LoginData.parse({
      access_token: 'abc',
      refresh_token: 'ref',
      token_type: 'Bearer',
      expires_in: 3600,
    })
    expect(d.access_token).toBe('abc')
    expect(d.token_type).toBe('Bearer')
  })

  it('缺失 access_token 即抛错', () => {
    expect(() => LoginData.parse({ refresh_token: 'ref' })).toThrow()
  })

  it('缺 refresh_token 仍可解析（optional）', () => {
    const d = LoginData.parse({ access_token: 'abc' })
    expect(d.token_type).toBe('Bearer')
    expect(d.refresh_token).toBeUndefined()
  })
})
