import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Markdown } from './Markdown'

describe('Markdown 渲染', () => {
  it('[S1] 引用转化为带提示的徽标', () => {
    render(<Markdown content={'结论见 [S1] 与 [S2]'} />)
    const badge = screen.getByTitle('引用来源 S1')
    expect(badge).toBeTruthy()
    expect(badge.textContent).toContain('S1')
  })

  it('标题与列表正常渲染', () => {
    render(<Markdown content={'# 一级标题\n\n- 点一\n- 点二'} />)
    expect(screen.getByText('一级标题')).toBeTruthy()
    expect(screen.getByText('点一')).toBeTruthy()
  })

  it('GFM 表格渲染为 table', () => {
    const { container } = render(
      <Markdown content={'| 指标 | 值 |\n| --- | --- |\n| PE | 20 |'} />,
    )
    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    expect(screen.getByText('PE')).toBeTruthy()
  })
})
