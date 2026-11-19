// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { openKLine, useKLineOverlayStore } from './klineOverlayStore'

const closeKLine = () => useKLineOverlayStore.getState().closeKLine()

// 用 stub 替换 KLineModal：把 props 渲染到 data-*，只验证桥接层转发是否正确，
// 不触碰 KLineModal 内部逻辑（关闭三件套 / 取数 / 空态由 KLineModal.test 覆盖）。
vi.mock('./KLineModal', () => ({
  KLineModal: (props: {
    open: boolean
    code: string | null
    name?: string
    priceDomain: string
  }) => (
    <div
      data-testid="kline-modal-stub"
      data-open={String(props.open)}
      data-code={props.code ?? ''}
      data-name={props.name ?? ''}
      data-domain={props.priceDomain}
    />
  ),
}))

import { GlobalKLineOverlay } from './GlobalKLineOverlay'

/** 每个用例前复位 store，避免用例间污染。 */
beforeEach(() => {
  cleanup()
  closeKLine()
})

describe('GlobalKLineOverlay · store → KLineModal 薄桥', () => {
  it('初始：无 code 时不打开（stub open=false）', () => {
    render(<GlobalKLineOverlay />)
    const stub = screen.getByTestId('kline-modal-stub')
    expect(stub.getAttribute('data-open')).toBe('false')
    expect(stub.getAttribute('data-code')).toBe('')
  })

  it('openKLine 带 code/name → stub 收到 open=true 且 code/name 正确', () => {
    render(<GlobalKLineOverlay />)
    act(() => openKLine('600519', '贵州茅台'))
    const stub = screen.getByTestId('kline-modal-stub')
    expect(stub.getAttribute('data-open')).toBe('true')
    expect(stub.getAttribute('data-code')).toBe('600519')
    expect(stub.getAttribute('data-name')).toBe('贵州茅台')
  })

  it('closeKLine 后 → stub open=false', () => {
    render(<GlobalKLineOverlay />)
    act(() => openKLine('600519', '贵州茅台'))
    expect(screen.getByTestId('kline-modal-stub').getAttribute('data-open')).toBe('true')
    act(() => closeKLine())
    expect(screen.getByTestId('kline-modal-stub').getAttribute('data-open')).toBe('false')
  })

  it('无 code（空串）调用 openKLine → 浮层仍不打开', () => {
    render(<GlobalKLineOverlay />)
    act(() => openKLine(''))
    expect(screen.getByTestId('kline-modal-stub').getAttribute('data-open')).toBe('false')
  })
})
