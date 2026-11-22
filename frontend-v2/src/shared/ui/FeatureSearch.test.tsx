import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { NAV } from '@/nav/nav'
import { FeatureSearch } from './FeatureSearch'

const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

beforeEach(() => vi.clearAllMocks())

describe('FeatureSearch · NAV 派生的顶栏功能搜索', () => {
  it('按功能名过滤，候选项显示功能名与所属分组', () => {
    render(<FeatureSearch />)
    const input = screen.getByRole('combobox', { name: '功能搜索' })
    fireEvent.change(input, { target: { value: '龙虎榜' } })
    const opts = screen.getAllByRole('option')
    expect(opts.length).toBeGreaterThan(0)
    expect(opts[0].textContent).toContain('龙虎榜')
    expect(opts[0].textContent).toContain('行情与市场')
  })

  it('按分组名也能命中功能', () => {
    render(<FeatureSearch />)
    const input = screen.getByRole('combobox', { name: '功能搜索' })
    // 2026-11-22 组名「决策与晨报」→「决策·晨报与助手」；按子串匹配用「晨报」更稳
    fireEvent.change(input, { target: { value: '晨报' } })
    const hits = screen.getAllByRole('option')
    expect(hits.length).toBeGreaterThan(0)
    expect(hits.every((o) => o.textContent?.includes('决策·晨报与助手'))).toBe(true)
  })

  it('空结果给中文提示，不编造功能', () => {
    render(<FeatureSearch />)
    fireEvent.change(screen.getByRole('combobox', { name: '功能搜索' }), {
      target: { value: '不存在的xyz功能' },
    })
    expect(screen.getByRole('status').textContent).toContain('未找到匹配的功能')
    expect(screen.queryAllByRole('option')).toHaveLength(0)
  })

  it('Enter 跳到 NAV 的 to（目标来自单一真理源，不硬编码）', () => {
    const target = NAV.flatMap((g) => g.items).find((it) => it.label === '龙虎榜')!
    render(<FeatureSearch />)
    const input = screen.getByRole('combobox', { name: '功能搜索' })
    fireEvent.change(input, { target: { value: '龙虎榜' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mockNavigate).toHaveBeenCalledWith({ to: target.to })
  })

  it('↑↓ 改变高亮项，Enter 跳到高亮项（目标来自 NAV）', () => {
    const candidates = NAV.flatMap((g) => g.items).filter((it) => it.label.includes('设置'))
    render(<FeatureSearch />)
    const input = screen.getByRole('combobox', { name: '功能搜索' })
    fireEvent.change(input, { target: { value: '设置' } })
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    const opts = screen.getAllByRole('option')
    const highlighted = opts.findIndex((o) => o.getAttribute('aria-selected') === 'true')
    expect(highlighted).toBeGreaterThanOrEqual(0)
    fireEvent.keyDown(input, { key: 'Enter' })
    const to = mockNavigate.mock.calls[0][0].to
    expect(candidates.map((c) => c.to)).toContain(to)
  })

  it('Esc 关闭下拉', () => {
    render(<FeatureSearch />)
    const input = screen.getByRole('combobox', { name: '功能搜索' })
    fireEvent.change(input, { target: { value: '概览' } })
    expect(input.getAttribute('aria-expanded')).toBe('true')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(input.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryAllByRole('option')).toHaveLength(0)
  })

  it('静态守卫：只从 NAV 派生，零硬编码 to="/..."', () => {
    const src = readFileSync(resolve(process.cwd(), 'src/shared/ui/FeatureSearch.tsx'), 'utf8')
    expect(src).toContain("from '@/nav/nav'")
    expect(src).toContain('NAV.flatMap')
    expect(src).not.toMatch(/to="\//)
    expect(src).not.toMatch(/to:\s*'\/[^']*'/)
  })
})
