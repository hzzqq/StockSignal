import { describe, it, expect } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CollapsibleCard, type CollapsibleCardProps } from './CollapsibleCard'

const CHILD = '展开后的完整表格内容'
const SUMMARY = '最新价 1523.5 · 权威数据日 2026-11-20'
const baseProps: CollapsibleCardProps = {
  title: '个股资金流明细',
  summary: SUMMARY,
  children: <div>{CHILD}</div>,
}

describe('CollapsibleCard · 通用折叠卡片', () => {
  it('默认折叠：children 不渲染，title/summary 仍可见，按钮 aria-expanded=false 且 aria-controls 指向存在节点', () => {
    render(<CollapsibleCard {...baseProps} />)
    expect(screen.queryByText(CHILD)).toBeNull()
    expect(screen.getByText('个股资金流明细')).toBeTruthy()
    expect(screen.getByText(SUMMARY)).toBeTruthy()
    const btn = screen.getByRole('button', { name: /展开/ })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
    const id = btn.getAttribute('aria-controls')
    expect(id).toBeTruthy()
    expect(document.getElementById(id!)).toBeTruthy()
  })

  it('点击展开显示 children、收起按钮 aria-expanded=true；再点收起恢复折叠态', () => {
    render(<CollapsibleCard {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: /展开/ }))
    expect(screen.getByText(CHILD)).toBeTruthy()
    const closeBtn = screen.getByRole('button', { name: /收起/ })
    expect(closeBtn.getAttribute('aria-expanded')).toBe('true')
    expect(screen.queryByText(SUMMARY)).toBeNull()
    fireEvent.click(closeBtn)
    expect(screen.queryByText(CHILD)).toBeNull()
    expect(screen.getByRole('button', { name: /展开/ }).getAttribute('aria-expanded')).toBe('false')
  })

  it('defaultOpen=true 默认展开；无 summary 时不渲染摘要行', () => {
    render(
      <CollapsibleCard title="默认展开卡" defaultOpen>
        <div>{CHILD}</div>
      </CollapsibleCard>,
    )
    expect(screen.getByText(CHILD)).toBeTruthy()
    expect(screen.getByRole('button', { name: /收起/ }).getAttribute('aria-expanded')).toBe('true')
  })

  it('折叠态摘要用 title 属性保留全文（truncate 不被截断丢失信息）', () => {
    render(<CollapsibleCard {...baseProps} />)
    expect(screen.getByText(SUMMARY).getAttribute('title')).toBe(SUMMARY)
  })

  it('section 为 region 语义并用 string 标题作为可访问名', () => {
    const { container } = render(<CollapsibleCard {...baseProps} />)
    const region = container.querySelector('[role="region"]')
    expect(region?.getAttribute('aria-label')).toBe('个股资金流明细')
  })
})
