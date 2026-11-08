import { describe, it, expect } from 'vitest'
import { resolveCompareSearch } from './deeplink'

describe('resolveCompareSearch 多股对比深链归一', () => {
  it('codes 逗号字符串 → 6 位数组，period 合法保留', () => {
    expect(resolveCompareSearch({ codes: '600519,000001', period: 'daily' })).toEqual({
      codes: ['600519', '000001'],
      period: 'daily',
    })
  })

  it('过滤非 6 位码，去重', () => {
    expect(resolveCompareSearch({ codes: '600519,abc,000001,600519' })).toEqual({
      codes: ['600519', '000001'],
    })
  })

  it('period 非法 → undefined（不写键）', () => {
    expect(resolveCompareSearch({ codes: '600519', period: 'yearly' })).toEqual({
      codes: ['600519'],
    })
  })

  it('空/缺省 → 空对象（不写键）', () => {
    expect(resolveCompareSearch({})).toEqual({})
    expect(resolveCompareSearch({ codes: 'abc', period: 'x' })).toEqual({})
  })

  it('codes 非字符串 → 忽略', () => {
    expect(resolveCompareSearch({ codes: 123 })).toEqual({})
  })
})
