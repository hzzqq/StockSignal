import { describe, it, expect } from 'vitest'
import {
  BUSINESS_DEGRADED_CODES,
  probeKind,
  type EndpointProbeResult,
} from '@/api/schemas/diagnostics'

function result(overrides: Partial<EndpointProbeResult> = {}): EndpointProbeResult {
  return {
    path: '/api/v2/read/x',
    httpStatus: 200,
    envelopeStatus: 'ok',
    envelopeCode: 'ok',
    ok: true,
    latencyMs: 1,
    detail: '正常',
    ...overrides,
  }
}

describe('probeKind · 业务诚实降级 vs 接口故障（绝不把 error 洗成成功）', () => {
  it('成功态 → ok', () => {
    expect(probeKind(result())).toBe('ok')
  })

  it('每个登记的业务码在 HTTP 200 + error 下都判 degraded', () => {
    for (const code of Object.keys(BUSINESS_DEGRADED_CODES)) {
      expect(
        probeKind(result({ ok: false, httpStatus: 200, envelopeStatus: 'error', envelopeCode: code })),
      ).toBe('degraded')
    }
  })

  it('参数错误 invalid_param / validation_error / bad_param 不是业务降级', () => {
    for (const code of ['invalid_param', 'validation_error', 'bad_param']) {
      expect(
        probeKind(result({ ok: false, httpStatus: 200, envelopeStatus: 'error', envelopeCode: code })),
      ).toBe('failure')
    }
  })

  it('非 2xx 即使带降级 code 也算接口故障', () => {
    expect(
      probeKind(result({ ok: false, httpStatus: 500, envelopeStatus: 'error', envelopeCode: 'unavailable' })),
    ).toBe('failure')
  })

  it('缺 code / 非 JSON 信封 / 网络异常都如实判故障，不静默降级', () => {
    expect(probeKind(result({ ok: false, envelopeStatus: 'error', envelopeCode: null }))).toBe('failure')
    expect(probeKind(result({ ok: false, envelopeStatus: null, envelopeCode: null }))).toBe('failure')
    expect(
      probeKind(result({ ok: false, httpStatus: null, envelopeStatus: null, envelopeCode: null })),
    ).toBe('failure')
  })
})
