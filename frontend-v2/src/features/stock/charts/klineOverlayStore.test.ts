import { beforeEach, describe, expect, it } from 'vitest'
import { openKLine, useKLineOverlayStore } from './klineOverlayStore'

/** 每个用例前复位 store，避免用例间污染。 */
beforeEach(() => {
  useKLineOverlayStore.getState().closeKLine()
})

describe('klineOverlayStore · 全局 K 线浮层状态', () => {
  it('初始关闭且 code=null', () => {
    const s = useKLineOverlayStore.getState()
    expect(s.open).toBe(false)
    expect(s.code).toBeNull()
    expect(s.name).toBeUndefined()
  })

  it('openKLine 带 code/name 后 open=true 且字段正确', () => {
    openKLine('600519', '贵州茅台')
    const s = useKLineOverlayStore.getState()
    expect(s.open).toBe(true)
    expect(s.code).toBe('600519')
    expect(s.name).toBe('贵州茅台')
  })

  it('openKLine 传空串不改状态（无标的不弹窗）', () => {
    openKLine('600519', '贵州茅台')
    openKLine('')
    const s = useKLineOverlayStore.getState()
    expect(s.open).toBe(true)
    expect(s.code).toBe('600519')
    expect(s.name).toBe('贵州茅台')
  })

  it('closeKLine 后 open=false 且回填安全值', () => {
    openKLine('000001', '平安银行', 'report')
    useKLineOverlayStore.getState().closeKLine()
    const s = useKLineOverlayStore.getState()
    expect(s.open).toBe(false)
    expect(s.code).toBeNull()
    expect(s.name).toBeUndefined()
    expect(s.priceDomain).toBe('market')
  })

  it('priceDomain 默认 market、可显式传 report', () => {
    openKLine('000001')
    expect(useKLineOverlayStore.getState().priceDomain).toBe('market')
    openKLine('000001', undefined, 'report')
    expect(useKLineOverlayStore.getState().priceDomain).toBe('report')
  })
})
