import { describe, it, expect } from 'vitest'
import { domainInk, inkForCell, classifyDomain } from './domainColor'

describe('domainInk 域级双色', () => {
  it('价格/行情域 → 交易屏 up 墨色 (--ss-up-ink)', () => {
    const priceFields = [
      'price', 'change_pct', 'pct_chg', 'open', 'high', 'low', 'pre_close',
      'volume', 'amount', 'pe', 'pb', 'ps', 'market_cap', 'turnover', 'amplitude',
      'ma5', 'ma20', 'ma60', 'rsi', 'macd', 'kdj', 'boll',
    ]
    for (const f of priceFields) {
      expect(domainInk(f)).toBe('var(--ss-up-ink)')
    }
  })

  it('业绩/报告域 → 报告体 up 墨色 (--doc-up-ink)', () => {
    const reportFields = [
      'revenue_yoy', 'revenue', 'profit', 'profit_yoy', 'growth', 'roe', 'margin', 'yoy',
    ]
    for (const f of reportFields) {
      expect(domainInk(f)).toBe('var(--doc-up-ink)')
    }
  })

  it('未知域 → 中性 (--sf-ink)', () => {
    expect(domainInk('note')).toBe('var(--sf-ink)')
    expect(domainInk('foo_bar')).toBe('var(--sf-ink)')
    expect(domainInk('name')).toBe('var(--sf-ink)')
  })

  it('classifyDomain 返回正确域', () => {
    expect(classifyDomain('price')).toBe('price')
    expect(classifyDomain('revenue_yoy')).toBe('report')
    expect(classifyDomain('name')).toBe('neutral')
  })
})

describe('inkForCell 方向降级', () => {
  it('价格域负值翻转到 down 墨色 (--ss-down-ink)', () => {
    expect(inkForCell('price', -1.2)).toBe('var(--ss-down-ink)')
  })
  it('业绩域负值翻转到 down 墨色 (--doc-down-ink)', () => {
    expect(inkForCell('revenue_yoy', -5)).toBe('var(--doc-down-ink)')
  })
  it('正值/非数字沿用域 up 墨色', () => {
    expect(inkForCell('price', 1.2)).toBe('var(--ss-up-ink)')
    expect(inkForCell('price', null)).toBe('var(--ss-up-ink)')
    expect(inkForCell('foo', 1)).toBe('var(--sf-ink)')
  })
})
