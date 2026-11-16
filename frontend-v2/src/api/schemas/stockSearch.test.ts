import { describe, it, expect } from 'vitest'
import {
  STOCK_MATCH_LABEL,
  StockSearchItemSchema,
  StockSearchResultSchema,
  stockMatchKind,
} from './stockSearch'

const moutai = {
  code: '600519',
  name: '贵州茅台',
  market: 'SH',
  asset_type: 'stock',
  pinyin_initials: 'gzmt',
  pinyin_full: 'guizhoumaotai',
  score: 1000,
}

describe('StockSearchItemSchema · 严格契约', () => {
  it('完整条目通过', () => {
    expect(StockSearchItemSchema.parse(moutai).code).toBe('600519')
  })

  it('允许后端省略可选字段与 score', () => {
    expect(StockSearchItemSchema.parse({ code: '000001', name: '平安银行' }).name).toBe('平安银行')
  })

  it('缺 code / 缺 name / 字段类型不符一律抛错，不兜底', () => {
    expect(() => StockSearchItemSchema.parse({ name: '贵州茅台' })).toThrow()
    expect(() => StockSearchItemSchema.parse({ code: '600519' })).toThrow()
    expect(() => StockSearchItemSchema.parse({ ...moutai, score: '1000' })).toThrow()
    expect(() => StockSearchResultSchema.parse([{ ...moutai, code: 600519 }])).toThrow()
  })

  it('空数组是合法结果（诚实无匹配）', () => {
    expect(StockSearchResultSchema.parse([])).toEqual([])
  })
})

describe('stockMatchKind · v1 匹配方式标签单一真理源', () => {
  it.each([
    ['600519', 'code_exact'],
    ['60051', 'code_prefix'],
    ['贵州茅台', 'name_exact'],
    ['茅台', 'name_contains'],
    ['gzmt', 'initials'],
    ['guizhoumaotai', 'full_pinyin'],
  ] as const)('%s -> %s', (q, kind) => {
    expect(stockMatchKind(q, moutai)).toBe(kind)
    expect(STOCK_MATCH_LABEL[kind]).toBeTruthy()
  })

  it('空查询与无命中都归为 other，不编造匹配方式', () => {
    expect(stockMatchKind('', moutai)).toBe('other')
    expect(stockMatchKind('zzzz', moutai)).toBe('other')
  })

  it('大小写不敏感', () => {
    expect(stockMatchKind('GZMT', moutai)).toBe('initials')
  })
})
