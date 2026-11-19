import { describe, expect, it } from 'vitest'
import { v1BandOf } from './BreadthOverview'

/**
 * 回归守卫（2026-11-19）：v1 BANDS 末档上界是 hi=101（modules/market_temperature.py:39），
 * 且 temperature_band:63 有 `return BANDS[-1]` 兜底。v2 曾把上界写成 100，导致温度恰好 100
 * 时派生档位返回 null，页面误报「温度不可得、不派生档位」。本守卫锁定边界值与缺失红线。
 */
describe('BreadthOverview · 按 v1 五档阈值派生温度档位', () => {
  it('温度恰好 100 判「狂热」（v1 末档 hi=101，不是显示区间 100）', () => {
    expect(v1BandOf(100)).toEqual({ label: '狂热', range: '80–100°' })
  })

  it('狂热档下界 80 与上界内侧 100.9 均判「狂热」', () => {
    expect(v1BandOf(80)?.label).toBe('狂热')
    expect(v1BandOf(100.9)?.label).toBe('狂热')
  })

  it('相邻档位边界不串档：79.9=活跃、60=活跃、59.9=中性、0=冰点', () => {
    expect(v1BandOf(79.9)?.label).toBe('活跃')
    expect(v1BandOf(60)?.label).toBe('活跃')
    expect(v1BandOf(59.9)?.label).toBe('中性')
    expect(v1BandOf(0)?.label).toBe('冰点')
    expect(v1BandOf(0)?.range).toBe('0–19°')
  })

  it('温度缺失（null/undefined/NaN）返回 null，页面继续显「—」不补零', () => {
    expect(v1BandOf(null)).toBeNull()
    expect(v1BandOf(undefined)).toBeNull()
    expect(v1BandOf(Number.NaN)).toBeNull()
    expect(v1BandOf(Infinity)).toBeNull()
  })

  it('数值可得但越界时落末档兜底（忠实 v1 BANDS[-1]），不误报不可得', () => {
    // 先钳制到 0–100，再按档位表派生：越界数值仍可得到档位，而非「温度不可得」。
    expect(v1BandOf(150)?.label).toBe('狂热')
    expect(v1BandOf(-10)?.label).toBe('冰点')
  })
})
