import { describe, it, expect } from 'vitest'
import { EnvelopeResponse, LoginData, parseEnvelope } from '@/api/schema'

describe('EnvelopeResponse — 严格校验，缺字段即抛错（禁止 ?? 0 兜底）', () => {
  it('解析合法信封', () => {
    const ok = EnvelopeResponse.parse({
      status: 'ok',
      code: 0,
      message: 'success',
      data: { a: 1 },
    })
    expect(ok.status).toBe('ok')
    expect(ok.data).toEqual({ a: 1 })
  })

  it('缺字段即抛错', () => {
    expect(() => EnvelopeResponse.parse({ status: 'ok', code: 0 })).toThrow()
    expect(() => EnvelopeResponse.parse({ status: 'ok', message: 'x', data: null })).toThrow()
  })

  it('code 非数字即抛错', () => {
    expect(() =>
      EnvelopeResponse.parse({ status: 'ok', code: 'bad', message: 'x', data: null }),
    ).toThrow()
  })

  it('status 非法枚举即抛错', () => {
    expect(() =>
      EnvelopeResponse.parse({ status: 'OK', code: 0, message: 'x', data: null }),
    ).toThrow()
  })

  it('parseEnvelope 与 EnvelopeResponse.parse 一致', () => {
    const raw = { status: 'error', code: 401, message: 'unauthorized', data: null }
    expect(parseEnvelope(raw)).toEqual(raw)
    expect(() => parseEnvelope({ status: 'error', code: 401, message: 'x' })).toThrow()
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
