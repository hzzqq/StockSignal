import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmptyStateModern } from './EmptyStateModern'

describe('EmptyStateModern · 层次化空态', () => {
  it('默认内联 SVG 空盒图标（24×24 / currentColor）', () => {
    const { container } = render(<EmptyStateModern title="暂无持仓" />)
    const icon = container.querySelector('svg')!
    expect(icon).toBeTruthy()
    expect(icon.getAttribute('viewBox')).toBe('0 0 24 24')
    expect(icon.getAttribute('stroke')).toBe('currentColor')
    expect(icon.getAttribute('aria-hidden')).toBe('true')
    expect(icon.parentElement!.className).toContain('text-sf-ink-3')
  })

  it('title / description 分层渲染，role=status', () => {
    render(
      <EmptyStateModern title="暂无持仓" description="同步后可查看真实数据" />,
    )
    const status = screen.getByRole('status')
    expect(status.className).toContain('py-12')
    expect(status.className).toContain('text-center')
    expect(screen.getByText('暂无持仓').className).toContain('text-page')
    expect(screen.getByText('同步后可查看真实数据').className).toContain('text-body')
  })

  it('action 渲染在底部且不编造业务数据', () => {
    render(
      <EmptyStateModern
        title="暂无数据"
        action={<button type="button">刷新数据</button>}
      />,
    )
    const btn = screen.getByRole('button', { name: '刷新数据' })
    expect(btn).toBeTruthy()
    expect(btn.parentElement!.className).toContain('mt-4')
    expect(screen.queryByText('同步后可查看真实数据')).toBeNull()
  })

  it('icon 可覆盖，className 合并', () => {
    const { container } = render(
      <EmptyStateModern
        title="空"
        icon={<span data-testid="custom-icon">C</span>}
        className="my-4"
      />,
    )
    expect(screen.getByTestId('custom-icon')).toBeTruthy()
    expect(container.querySelector('svg')).toBeNull()
    expect(screen.getByRole('status').className).toContain('my-4')
  })
})
