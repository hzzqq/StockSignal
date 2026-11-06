import { describe, it, expect } from 'vitest'
import {
  freshnessLevelFromAge,
  freshnessFromStatus,
  freshnessLabel,
  FRESH_WARN_DAYS,
  FRESH_STALE_DAYS,
} from '@/lib/freshness'

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
