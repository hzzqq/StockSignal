import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Skeleton } from './Skeleton'

describe('Skeleton · 骨架屏', () => {
  it('默认 rows=1：一条占位 + role=status + sr-only「加载中」', () => {
    const { container } = render(<Skeleton />)
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBe(1)
    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText('加载中')).toBeTruthy()
  })

  it('rows=3：渲染 3 条占位且都带 animate-pulse / bg-sf-surface-2', () => {
    const { container } = render(<Skeleton rows={3} />)
    const bars = container.querySelectorAll('[aria-hidden="true"]')
    expect(bars.length).toBe(3)
    bars.forEach((bar) => {
      expect(bar.className).toContain('animate-pulse')
      expect(bar.className).toContain('bg-sf-surface-2')
    })
  })

  it('variant=card / circle 使用对应圆角与形状', () => {
    const card = render(<Skeleton variant="card" />)
    expect(card.container.querySelector('[aria-hidden="true"]')!.className).toContain(
      'rounded-card',
    )
    const circle = render(<Skeleton variant="circle" />)
    expect(circle.container.querySelector('[aria-hidden="true"]')!.className).toContain(
      'rounded-full',
    )
  })

  it('className 合并且 rows=0 时无视觉占位（仍保留状态语义）', () => {
    const { container } = render(<Skeleton rows={0} className="my-2" />)
    expect(container.firstElementChild!.className).toContain('my-2')
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBe(0)
    expect(screen.getByRole('status')).toBeTruthy()
  })
})
