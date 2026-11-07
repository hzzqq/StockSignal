import { describe, expect, it } from 'vitest'
import { resolveResearchSearch, resolveLegacySearch } from '@/lib/deeplink'

/**
 * W4-B · 深链归一纯函数单测（零 DOM 依赖）。
 * 覆盖 view 回落（缺/非法/'quick'/中文）、code 6 位校验（非法不写键）、
 * pick_stock 单独 → quick、'🔬 深度分析' + code → deep、非法 code 不进入最终 search。
 */
describe('resolveResearchSearch', () => {
  it('缺 view → quick，且不含 code 键', () => {
    const r = resolveResearchSearch({})
    expect(r).toEqual({ view: 'quick' })
    expect('code' in r).toBe(false)
  })

  it("view='deep' → deep；view='quick' → quick", () => {
    expect(resolveResearchSearch({ view: 'deep' })).toEqual({ view: 'deep' })
    expect(resolveResearchSearch({ view: 'quick' })).toEqual({ view: 'quick' })
  })

  it('非法 view（含中文旧值）一律回落 quick', () => {
    expect(resolveResearchSearch({ view: 'garbage' })).toEqual({ view: 'quick' })
    expect(resolveResearchSearch({ view: '🔬 深度分析' })).toEqual({ view: 'quick' })
    expect(resolveResearchSearch({ view: 1 })).toEqual({ view: 'quick' })
  })

  it('合法 6 位 code 保留并写键', () => {
    expect(resolveResearchSearch({ view: 'deep', code: '000001' })).toEqual({
      view: 'deep',
      code: '000001',
    })
  })

  it("非法 code 不写 code 键（禁 ?? '' 兜底）", () => {
    for (const code of ['abc', '60051', '6005190', 600519, null, undefined, {}]) {
      const r = resolveResearchSearch({ view: 'deep', code })
      expect(r).toEqual({ view: 'deep' })
      expect('code' in r).toBe(false)
    }
  })
})

describe('resolveLegacySearch', () => {
  it("hub_gyj_view='🔬 深度分析' → deep（中文旧链接真值）", () => {
    expect(resolveLegacySearch({ hub_gyj_view: '🔬 深度分析' })).toEqual({ view: 'deep' })
  })

  it("hub_gyj_view='deep' → deep；'⚡ 快速选取'/'quick'/缺/非法 → quick", () => {
    expect(resolveLegacySearch({ hub_gyj_view: 'deep' })).toEqual({ view: 'deep' })
    expect(resolveLegacySearch({ hub_gyj_view: '⚡ 快速选取' })).toEqual({ view: 'quick' })
    expect(resolveLegacySearch({ hub_gyj_view: 'quick' })).toEqual({ view: 'quick' })
    expect(resolveLegacySearch({ hub_gyj_view: 'garbage' })).toEqual({ view: 'quick' })
    expect(resolveLegacySearch({})).toEqual({ view: 'quick' })
  })

  it('只传 pick_stock、不带 hub_gyj_view → view=quick（旧 22:864-866 真值）', () => {
    expect(resolveLegacySearch({ pick_stock: '600519' })).toEqual({
      view: 'quick',
      code: '600519',
    })
  })

  it("'🔬 深度分析' + 合法 code → deep + code", () => {
    expect(resolveLegacySearch({ hub_gyj_view: '🔬 深度分析', pick_stock: '000001' })).toEqual({
      view: 'deep',
      code: '000001',
    })
  })

  it('非法 pick_stock 不写 code 键', () => {
    for (const pick_stock of ['abc', '60051', 600519, null, undefined]) {
      const r = resolveLegacySearch({ hub_gyj_view: 'deep', pick_stock })
      expect(r).toEqual({ view: 'deep' })
      expect('code' in r).toBe(false)
    }
  })

  it('缺全部参数 → quick 且不含 code 键', () => {
    const r = resolveLegacySearch({})
    expect(r).toEqual({ view: 'quick' })
    expect('code' in r).toBe(false)
  })
})
