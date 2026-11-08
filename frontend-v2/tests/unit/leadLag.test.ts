import { describe, expect, it } from 'vitest'
import type { BreadthHistoryPoint } from '@/api/schemas/read'
import {
  DIMENSIONS, EXCLUDED_DIMENSIONS, DERIVED_NOTICE, MIN_SAMPLES, MIN_PAIR_SAMPLES, MAX_LAG,
  valuesOf, validCount, isNearConstant, pearson, signedLag, bestLag, buildMatrix,
  type LeadLagResult,
} from '@/lib/leadLag'

/**
 * 维度领先-滞后矩阵的真实计算回归。
 *
 * 守的不是「跑通」，而是 v1 `modules/lead_lag_matrix.py` 的口径与诚实红线：
 * 有序对（含反向）、带符号 lag、null 不补 0、样本不足/近乎常数如实列出、
 * 离线缺真值维度绝不进矩阵、机械相关必须披露。
 */
function day(i: number): string {
  return new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10)
}

function series(n: number, override?: (i: number) => Record<string, unknown>): BreadthHistoryPoint[] {
  return Array.from({ length: n }, (_, i) => {
    const row: Record<string, unknown> = {
      date: day(i),
      up_count: 1000 + (i % 7) * 137,
      down_count: 3000 - (i % 5) * 211,
      flat_count: 5 + (i % 3),
      limit_up: 10 + (i % 11) * 3,
      limit_down: 3 + (i % 4),
      red_ratio: 20 + (i % 9) * 4,
    }
    if (override) Object.assign(row, override(i))
    return row as unknown as BreadthHistoryPoint
  })
}

describe('口径常量与数据边界', () => {
  it('可靠维度与 v1 REAL_FEATURES 逐项一致，被剔除字段不与之重叠', () => {
    expect(DIMENSIONS.map((d) => d.key)).toEqual([
      'up_count', 'down_count', 'flat_count', 'limit_up', 'limit_down', 'red_ratio',
    ])
    const reliable = new Set(DIMENSIONS.map((d) => d.key))
    expect(EXCLUDED_DIMENSIONS.length).toBeGreaterThan(0)
    expect(EXCLUDED_DIMENSIONS.every((d) => !reliable.has(d.key))).toBe(true)
    expect(EXCLUDED_DIMENSIONS.some((d) => d.key === 'connect_hl')).toBe(true)
  })

  it('机械相关警示必须点名 red_ratio 与派生关系，不能只写「注意」', () => {
    expect(DERIVED_NOTICE).toContain('red_ratio')
    expect(DERIVED_NOTICE).toContain('机械相关')
    expect(DERIVED_NOTICE).toContain('上涨')
  })

  it('样本门槛比 v1 更严格，窗口与 v1 一致', () => {
    expect(MIN_SAMPLES).toBeGreaterThanOrEqual(30)
    expect(MIN_PAIR_SAMPLES).toBeGreaterThanOrEqual(30)
    expect(MAX_LAG).toBe(20)
  })
})

describe('取值与相关系数：不补 0、不造数', () => {
  it('null / 字符串 / NaN 一律为 null，validCount 只数真数字', () => {
    const s = series(3, (i) => ({
      up_count: i === 0 ? null : i === 1 ? 'not-a-number' : Number.NaN,
    }))
    expect(valuesOf(s, 'up_count')).toEqual([null, null, null])
    expect(validCount(valuesOf(s, 'up_count'))).toBe(0)
    expect(validCount([1, null, 2, Number.NaN as unknown as number, 3])).toBe(3)
  })

  it('pearson 正负相关、常量与样本不足都给真结果', () => {
    const a = Array.from({ length: 40 }, (_, i) => Math.sin(i * 0.7) * 10 + i)
    expect(pearson(a, a)).toBeCloseTo(1, 10)
    expect(pearson(a, a.map((v) => -v))).toBeCloseTo(-1, 10)
    expect(pearson(a, new Array(40).fill(7))).toBeNull()
    expect(pearson(a.slice(0, MIN_PAIR_SAMPLES - 1), a.slice(0, MIN_PAIR_SAMPLES - 1))).toBeNull()
  })

  it('isNearConstant 识别常数序列，放过有波动的序列', () => {
    expect(isNearConstant(new Array(40).fill(100))).toBe(true)
    expect(isNearConstant([null, null])).toBe(true)
    expect(isNearConstant(Array.from({ length: 40 }, (_, i) => 100 + (i % 7)))).toBe(false)
  })
})

describe('有序对与带符号 lag（对齐 v1 n×n 矩阵）', () => {
  const A = { key: 'a', label: 'A' }
  const B = { key: 'b', label: 'B' }

  it('signedLag：正相关记 +k，负相关记 -k', () => {
    const base: LeadLagResult = {
      x: 'a', y: 'b', xLabel: 'A', yLabel: 'B',
      lag: 3, corr: 0.8, samples: 40, evaluatedLags: 5,
    }
    expect(signedLag(base)).toBe(3)
    expect(signedLag({ ...base, corr: -0.8 })).toBe(-3)
    expect(signedLag({ ...base, lag: 0, corr: -0.8 })).toBe(0)
  })

  it('bestLag 真的找出平移 2 日的领先关系，反向有序对不是同一个 lag', () => {
    const xs = Array.from({ length: 40 }, (_, i) => Math.sin(i * 0.7) * 10 + (i % 3))
    const ys: (number | null)[] = [null, null, ...xs.slice(0, 38)]
    const forward = bestLag(xs, ys, A, B)
    expect(forward?.lag).toBe(2)
    expect(forward?.corr).toBeCloseTo(1, 6)
    expect(forward?.samples).toBe(38)
    const backward = bestLag(ys, xs, B, A)
    expect(backward).toBeTruthy()
    expect(backward?.lag).not.toBe(2)
  })

  it('buildMatrix 输出全部有序对 i≠j（6 维 → 30 组），且按数据日排序', () => {
    const m = buildMatrix(series(40))
    expect(m.excluded).toHaveLength(0)
    expect(m.skippedPairs).toHaveLength(0)
    expect(m.rows).toHaveLength(DIMENSIONS.length * (DIMENSIONS.length - 1))
    expect(m.rows.every((r) => r.x !== r.y)).toBe(true)
    const pairs = new Set(m.rows.map((r) => `${r.x}->${r.y}`))
    expect(pairs.size).toBe(30)
    expect(pairs.has('up_count->down_count')).toBe(true)
    expect(pairs.has('down_count->up_count')).toBe(true)
    expect(m.firstDate).toBe(day(0))
    expect(m.lastDate).toBe(day(39))
    expect(m.totalDays).toBe(40)
    expect(m.usableDays).toBe(40)

    const reversed = buildMatrix([...series(40)].reverse())
    expect(reversed.firstDate).toBe(day(0))
    expect(reversed.lastDate).toBe(day(39))
    expect(reversed.rows.map((r) => `${r.x}->${r.y}`)).toEqual(m.rows.map((r) => `${r.x}->${r.y}`))
  })

  it('离线缺真值维度即使被填满数值也绝不进矩阵', () => {
    const m = buildMatrix(series(40, (i) => ({
      connect_hl: i + 1, connect_2b: i % 4, zt_fail_ratio: i % 5,
      fc_ratio: i % 3, zt_prev_ret: i / 10, touch_down: i % 2,
    })))
    const excludedKeys = new Set(EXCLUDED_DIMENSIONS.map((d) => d.key))
    expect(m.rows.length).toBeGreaterThan(0)
    expect(m.rows.every((r) => !excludedKeys.has(r.x) && !excludedKeys.has(r.y))).toBe(true)
  })
})

describe('诚实降级：不足不静默', () => {
  it('只有 3 个交易日 → 不产出任何相关系数，6 个维度如实列出原因', () => {
    const m = buildMatrix(series(3))
    expect(m.rows).toHaveLength(0)
    expect(m.skippedPairs).toHaveLength(0)
    expect(m.excluded).toHaveLength(6)
    expect(m.excluded.every((e) => e.samples === 3)).toBe(true)
    expect(m.excluded[0].reason).toContain('有效样本')
    expect(m.totalDays).toBe(3)
  })

  it('近乎常数维度被剔除，且不出现在任何有序对里', () => {
    const m = buildMatrix(series(40, () => ({ up_count: 100 })))
    const hit = m.excluded.find((e) => e.key === 'up_count')
    expect(hit?.reason).toContain('近乎常数')
    expect(m.rows.every((r) => r.x !== 'up_count' && r.y !== 'up_count')).toBe(true)
    expect(m.rows).toHaveLength(5 * 4)
  })

  it('两个维度各 30 个有效日但时间完全错开 → 成对样本不足的对如实列出，不静默消失', () => {
    const s: BreadthHistoryPoint[] = Array.from({ length: 60 }, (_, i) => ({
      date: day(i),
      up_count: i < 30 ? 1000 + (i % 7) * 137 : null,
      down_count: i >= 30 ? 3000 - ((i - 30) % 5) * 211 : null,
      flat_count: null, limit_up: null, limit_down: null, red_ratio: null,
    }))
    const m = buildMatrix(s)
    expect(m.excluded).toHaveLength(4)
    expect(m.rows).toHaveLength(0)
    expect(m.skippedPairs).toHaveLength(2)
    expect(m.skippedPairs.every((p) => p.reason.includes('成对样本'))).toBe(true)
    expect(m.skippedPairs.map((p) => `${p.x}->${p.y}`).sort()).toEqual([
      'down_count->up_count', 'up_count->down_count',
    ])
  })
})
