import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScoreBar } from './ScoreBar'

const meter = (c: HTMLElement) => c.querySelector('[role="meter"]') as HTMLElement | null

describe('ScoreBar · 评分进度条（诚实缺失 + 0-100 clamp）', () => {
  it('value=null：显示「—」、不渲染填充条、无 aria-valuenow（绝不补 0/50）', () => {
    const { container } = render(<ScoreBar label="综合评分" value={null} />)
    expect(screen.getByText('—')).toBeTruthy()
    expect(screen.queryByRole('meter')).toBeNull()
    expect(container.querySelector('[aria-valuenow]')).toBeNull()
    expect(container.textContent).not.toContain('50')
  })

  it('value=85：宽度 85%、aria-valuenow=85，meter 语义完整', () => {
    const { container } = render(<ScoreBar label="综合评分" value={85} />)
    const m = meter(container)!
    expect(m.getAttribute('aria-valuenow')).toBe('85')
    expect(m.getAttribute('aria-valuemin')).toBe('0')
    expect(m.getAttribute('aria-valuemax')).toBe('100')
    expect(m.getAttribute('aria-label')).toBe('综合评分')
    expect(m.style.width).toBe('85%')
    expect(screen.getByRole('meter', { name: '综合评分' })).toBeTruthy()
  })

  it('越界值 clamp：150 -> 100% / aria-valuenow=100，-10 -> 0% / aria-valuenow=0', () => {
    const hi = render(<ScoreBar label="高分项" value={150} />)
    expect(meter(hi.container)!.getAttribute('aria-valuenow')).toBe('100')
    expect(meter(hi.container)!.style.width).toBe('100%')

    const lo = render(<ScoreBar label="低分项" value={-10} />)
    expect(meter(lo.container)!.getAttribute('aria-valuenow')).toBe('0')
    expect(meter(lo.container)!.style.width).toBe('0%')
  })

  it('缺省色用 accent 令牌（评分不是涨跌，不借价格域红绿）；color 可覆盖', () => {
    const def = render(<ScoreBar label="默认项" value={60} />)
    expect(meter(def.container)!.getAttribute('style') ?? '').toContain('--color-sf-accent')
    const custom = render(<ScoreBar label="自定义项" value={60} color="rgb(1, 2, 3)" />)
    expect(meter(custom.container)!.style.backgroundColor).toBe('rgb(1, 2, 3)')
  })

  it('NaN / Infinity 视为缺失：显示「—」，不画条（诚实边界）', () => {
    const nan = render(<ScoreBar label="非法值" value={Number.NaN} />)
    expect(screen.getByText('—')).toBeTruthy()
    expect(meter(nan.container)).toBeNull()
  })
})
