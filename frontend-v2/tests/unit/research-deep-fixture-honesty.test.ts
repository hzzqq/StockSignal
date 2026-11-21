/**
 * research-deep 夹具诚实守卫 —— 防止 MSW 夹具造假污染「豁免态展示真实字段」的新行为。
 *
 * 真后端 read_routes.research_deep()（backend/api/read_routes.py:2145）对任意 6 位 code
 * 返回的字段全集固定为下列 16 键；pb/turnover 恒 null；无额外技术指标/财务派生键；
 * deep_analysis_available 恒 false（56 键 analysis_engine 异步深度分析本轮未接入）。
 * 夹具若偷偷塞入假数据，在「豁免态仍渲染真实字段」的新前端行为下会直接展示给用户。
 */
import { describe, it, expect } from 'vitest'
import { researchDeepFull } from '@/mocks/fixtures'

/** 真后端 research_deep 返回的字段白名单（顺序无关，断言时排序比较）。 */
const BACKEND_FIELD_SET = [
  'code', 'name', 'industry', 'date', 'price', 'pe_ttm', 'pb', 'market_cap',
  'ma5', 'ma10', 'ma20', 'ma60', 'amplitude', 'turnover',
  'deep_analysis_available', 'note',
].sort()

/** 后端 research_deep 从不返回的伪造键（旧夹具曾全部造假塞入）。 */
const FAKE_KEYS = [
  'rsi', 'macd', 'kdj', 'boll',
  'revenue_yoy', 'profit_yoy', 'roe', 'gross_margin',
]

describe('researchDeepFull 夹具诚实守卫（对齐真后端 research_deep 口径）', () => {
  it('不得包含后端从不返回的伪造技术服务/财务键', () => {
    const present = FAKE_KEYS.filter((k) => k in researchDeepFull)
    expect(
      present,
      `夹具塞入了后端 research_deep 从不返回的键：${present.join(', ')}`,
    ).toEqual([])
  })

  it('pb 与 turnover 恒为 null（真后端无 pb 源 / 无流通股本源）', () => {
    expect(researchDeepFull.pb).toBeNull()
    expect(researchDeepFull.turnover).toBeNull()
  })

  it('deep_analysis_available 恒为 false（异步深度分析未接入）', () => {
    expect(researchDeepFull.deep_analysis_available).toBe(false)
  })

  it('字段集合与真后端 16 键白名单完全一致（无多键、无缺键）', () => {
    const actual = Object.keys(researchDeepFull).sort()
    expect(
      actual,
      `夹具字段与真后端白名单漂移：实际=${actual.join(',')}；应=${BACKEND_FIELD_SET.join(',')}`,
    ).toEqual(BACKEND_FIELD_SET)
  })

  it('name/industry/date 即便为 null 也只在白名单内（诚实空态允许 null）', () => {
    // 反向锁定：允许 null，但不允许这三个字段缺失或出现白名单外字段。
    for (const k of ['name', 'industry', 'date']) {
      expect(k in researchDeepFull, `真后端固定返回 ${k} 键，夹具不得缺失`).toBe(true)
    }
    expect(researchDeepFull.industry).toBeNull()
  })
})
