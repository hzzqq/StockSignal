import { describe, it, expect } from 'vitest'
import {
  freshnessLevelFromAge,
  freshnessFromStatus,
  freshnessLabel,
  FRESH_WARN_DAYS,
  FRESH_STALE_DAYS,
} from '@/lib/freshness'
import { worstFreshness, freshnessOfSnapshot } from '@/lib/freshness'

describe('freshnessLevelFromAge', () => {
  it('0 天 → ok', () => expect(freshnessLevelFromAge(0)).toBe('ok'))
  it('≤WARN → ok', () => expect(freshnessLevelFromAge(FRESH_WARN_DAYS)).toBe('ok'))
  it('WARN+1 → warn', () => expect(freshnessLevelFromAge(FRESH_WARN_DAYS + 1)).toBe('warn'))
  it('≤STALE → warn', () => expect(freshnessLevelFromAge(FRESH_STALE_DAYS)).toBe('warn'))
  it('STALE+1 → stale', () => expect(freshnessLevelFromAge(FRESH_STALE_DAYS + 1)).toBe('stale'))
  it('null/undefined/负数 → unknown', () => {
    expect(freshnessLevelFromAge(null)).toBe('unknown')
    expect(freshnessLevelFromAge(undefined)).toBe('unknown')
    expect(freshnessLevelFromAge(-1)).toBe('unknown')
  })
})

describe('freshnessFromStatus', () => {
  it('ok/warn/stale 映射', () => {
    expect(freshnessFromStatus('ok')).toBe('ok')
    expect(freshnessFromStatus('WARN')).toBe('warn')
    expect(freshnessFromStatus('stale')).toBe('stale')
    expect(freshnessFromStatus(undefined)).toBe('unknown')
  })
})

describe('freshnessLabel', () => {
  it('映射中文标签', () => {
    expect(freshnessLabel('stale')).toBe('数据陈旧')
    expect(freshnessLabel('warn')).toBe('数据偏旧')
    expect(freshnessLabel('ok')).toBe('数据新鲜')
    expect(freshnessLabel('unknown')).toBe('新鲜度未知')
  })
})

describe('worstFreshness / freshnessOfSnapshot', () => {
  it('全 unknown（含空参）→ unknown；unknown 不参与比较', () => {
    expect(worstFreshness()).toBe('unknown')
    expect(worstFreshness('unknown', 'unknown')).toBe('unknown')
    expect(worstFreshness('unknown', 'ok')).toBe('ok')
  })

  it('ok + stale → stale（取更差档，与参数顺序无关）', () => {
    expect(worstFreshness('ok', 'stale')).toBe('stale')
    expect(worstFreshness('stale', 'ok')).toBe('stale')
  })

  it('warn + ok → warn（取更差档，与参数顺序无关）', () => {
    expect(worstFreshness('warn', 'ok')).toBe('warn')
    expect(worstFreshness('ok', 'warn')).toBe('warn')
  })

  it('freshnessOfSnapshot：age/status 双通道取更差，age=0 不掩盖 status=stale', () => {
    expect(freshnessOfSnapshot({ data_age_days: 0, data_freshness: { status: 'stale' } })).toBe('stale')
    expect(freshnessOfSnapshot({ data_age_days: 6, data_freshness: { status: 'ok' } })).toBe('warn')
    expect(freshnessOfSnapshot({ data_age_days: 2, data_freshness: { status: 'warn' } })).toBe('warn')
    expect(freshnessOfSnapshot({ data_age_days: 10, data_freshness: { status: 'ok' } })).toBe('stale')
  })

  it('freshnessOfSnapshot：缺字段 / null / 单通道 → 不乐观兜底', () => {
    expect(freshnessOfSnapshot({})).toBe('unknown')
    expect(freshnessOfSnapshot({ data_age_days: null, data_freshness: null })).toBe('unknown')
    expect(freshnessOfSnapshot({ data_age_days: 2 })).toBe('ok')
    expect(freshnessOfSnapshot({ data_freshness: { status: 'stale' } })).toBe('stale')
    expect(freshnessOfSnapshot({ data_freshness: {} })).toBe('unknown')
  })
})
