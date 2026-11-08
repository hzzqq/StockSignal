// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'

/**
 * MSW 与真后端的契约守卫（真发请求，不靠「handlers 数组非空」空转）。
 *
 * 真实故障（2026-11-09）：旧夹具给缺参端点补默认参数、把未知快照日期回退今日、
 * 把 research-deep 的 600519 伪造成「深度分析已接入」，开发态全绿，
 * 接真实后端时接口检测大面积假报、页面拿到与真后端不同的数据形态。
 */
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

async function read(path: string) {
  // 与 e2e 测试一致用同源相对路径：跨源绝对 URL 在 jsdom 下会拿到空响应，
  // 让守卫以假失败收场。空响应/非 JSON 直接报明路径与片段，不静默吞掉。
  const res = await fetch(path)
  const raw = await res.text()
  if (!raw) throw new Error(`空响应：${path} HTTP ${res.status}`)
  try {
    return { status: res.status, body: JSON.parse(raw) as Record<string, any> }
  } catch {
    throw new Error(`响应不是 JSON：${path} HTTP ${res.status} ${raw.slice(0, 120)}`)
  }
}

describe('MSW handlers 数量与基础形态', () => {
  it('路由数量与端点覆盖不退化（不是只断言数组非空）', () => {
    expect(Array.isArray(handlers)).toBe(true)
    expect(handlers.length).toBeGreaterThanOrEqual(30)
  })

  it('健康检测带 msw-mock 标记，前端可据实识别模拟来源', async () => {
    const { status, body } = await read('/api/health')
    expect(status).toBe(200)
    expect(body.status).toBe('ok')
    expect(body.data.source).toBe('msw-mock')
  })
})

describe('缺参端点必须对齐真后端的 400 / not_found', () => {
  it('paper-trades 缺 user → 400 validation_error（不得默认 admin）', async () => {
    const { status, body } = await read('/api/v2/read/paper-trades')
    expect(status).toBe(400)
    expect(body.code).toBe('validation_error')
  })

  it('paper-trades 合法 user → 真实账本；未知 user → not_found 而非回退 admin', async () => {
    const known = await read('/api/v2/read/paper-trades?user=admin')
    expect(known.status).toBe(200)
    expect(known.body.status).toBe('ok')
    expect(known.body.data.init_cash).toBe(1000000)

    const unknown = await read('/api/v2/read/paper-trades?user=ghost')
    expect(unknown.status).toBe(200)
    expect(unknown.body.status).toBe('error')
    expect(unknown.body.code).toBe('not_found')
  })

  it('paper-trades 非法 user → 400', async () => {
    const { status } = await read('/api/v2/read/paper-trades?user=bad-user!')
    expect(status).toBe(400)
  })

  it('review-notes 缺 date / 假日期 → 400；合法日期但无文件 → not_found', async () => {
    expect((await read('/api/v2/read/review-notes')).status).toBe(400)
    expect((await read('/api/v2/read/review-notes?date=2026-13-99')).status).toBe(400)
    const missing = await read('/api/v2/read/review-notes?date=2026-09-21')
    expect(missing.status).toBe(200)
    expect(missing.body.code).toBe('not_found')
  })
})

describe('历史快照不得回退今日快照冒充回放', () => {
  it('已有归档日期返回该日期的快照', async () => {
    const { status, body } = await read('/api/v2/read/snapshot/2026-09-21')
    expect(status).toBe(200)
    expect(body.status).toBe('ok')
    expect(body.data.date).toBe('2026-09-21')
  })

  it('日期清单里存在但无归档的 2026-11-06 → not_found，绝不回退今日', async () => {
    const { status, body } = await read('/api/v2/read/snapshot/2026-11-06')
    expect(status).toBe(200)
    expect(body.status).toBe('error')
    expect(body.code).toBe('not_found')
  })

  it('非法日期 / 不存在的日历日 → 400', async () => {
    expect((await read('/api/v2/read/snapshot/not-a-date')).status).toBe(400)
    expect((await read('/api/v2/read/snapshot/2026-02-30')).status).toBe(400)
  })
})

describe('research-deep 不得伪造「56 键深度分析已接入」', () => {
  it('600519 恒 deep_analysis_available=false，与真后端一致', async () => {
    const { status, body } = await read('/api/v2/read/research-deep?code=600519')
    expect(status).toBe(200)
    expect(body.status).toBe('ok')
    expect(body.data.deep_analysis_available).toBe(false)
    expect(body.data.ma5).toBeDefined()
  })

  it('其余合法码同样为 false；缺 code → 400 invalid_param', async () => {
    const other = await read('/api/v2/read/research-deep?code=000001')
    expect(other.body.data.deep_analysis_available).toBe(false)
    const bad = await read('/api/v2/read/research-deep')
    expect(bad.status).toBe(400)
    expect(bad.body.code).toBe('invalid_param')
  })
})
