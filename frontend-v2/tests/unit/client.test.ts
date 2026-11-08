// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, ApiError } from '@/api/client'

/**
 * apiFetch 错误通道守卫。
 * 真实故障（2026-11-09）：非 JSON 的 502/504/HTML 网关错误页直接走 res.json()，
 * 抛 SyntaxError，HTTP 状态与响应片段全丢，页面只显示 "Unexpected token <"。
 */
function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, statusText: 'x', headers: { 'Content-Type': 'application/json' } })
}

function envelope(status: 'ok' | 'error', code: string, message: string, data: unknown) {
  return { status, code, message, data }
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('apiFetch · 非 JSON / 非信封错误必须保留 HTTP 状态', () => {
  it('502 HTML 网关错误页 → ApiError(http_error)，带状态码与响应片段', async () => {
    // 每个请求返回全新 Response：Response body 只能消费一次，复用会让守卫假失败。
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(
      new Response('<html><body>502 Bad Gateway</body></html>', { status: 502, statusText: 'Bad Gateway' }),
    )))
    const err = await apiFetch('/v2/read/daily-snapshot').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('http_error')
    expect((err as ApiError).message).toContain('HTTP 502')
    expect((err as ApiError).message).toContain('502 Bad Gateway')
  })

  it('504 空响应 → 明确写出「空响应」，不是 SyntaxError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response('', { status: 504 }))))
    await expect(apiFetch('/whatever')).rejects.toMatchObject({
      code: 'http_error',
      message: expect.stringContaining('空响应'),
    })
  })

  it('200 但不是统一信封 → 带 HTTP 200 和原始片段，不静默当成功', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(200, { foo: 1 }))))
    const err = await apiFetch('/whatever').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('http_error')
    expect((err as ApiError).message).toContain('HTTP 200')
    expect((err as ApiError).message).toContain('不符合统一信封')
  })
})

describe('apiFetch · 正常与业务错误通道不回退', () => {
  it('合法 ok 信封 → 原样返回 data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, envelope('ok', 'ok', 'ok', { a: 1 }))))
    await expect(apiFetch<{ a: number }>('/x')).resolves.toEqual({ a: 1 })
  })

  it('后端业务错误信封 → ApiError 带后端 code 与 message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, envelope('error', 'not_found', '数据文件缺失', null))))
    await expect(apiFetch('/x')).rejects.toMatchObject({
      code: 'not_found',
      message: '数据文件缺失',
    })
  })

  it('401 单飞刷新后重试仍走新信封解析，data 不丢', async () => {
    localStorage.setItem('ss_refresh', 'ref')
    const calls: string[] = []
    const fetchMock = vi.fn(async (url: string) => {
      calls.push(String(url))
      if (calls.length === 1) return new Response('', { status: 401 })
      if (calls.length === 2) return jsonResponse(200, envelope('ok', 'ok', 'ok', { access_token: 'new-token' }))
      return jsonResponse(200, envelope('ok', 'ok', 'ok', { hit: true }))
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(apiFetch<{ hit: boolean }>('/x')).resolves.toEqual({ hit: true })
    expect(calls).toHaveLength(3)
    expect(localStorage.getItem('ss_token')).toBe('new-token')
  })
})

describe('ApiError 形态', () => {
  it('保留 code / reason 字段供上层分流', () => {
    const e = new ApiError('unauthorized', '请重新登录')
    expect(e).toBeInstanceOf(Error)
    expect(e.name).toBe('ApiError')
    expect(e.code).toBe('unauthorized')
    expect(e.reason).toBe('请重新登录')
  })
})
