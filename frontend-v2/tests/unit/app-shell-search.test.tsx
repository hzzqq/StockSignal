// @vitest-environment jsdom
/**
 * 顶栏搜索行为守卫：股票搜索命中后跳个股研究页并带 code（不再开全局 K 线浮层），
 * 以及窄屏(<768px)搜索入口的展开/收起。
 *
 * 用「一键选中」桩替掉 StockSearchInput，只验证 AppShell 的命中接线，
 * 不重复测输入组件自身的防抖与键盘交互（那部分由 StockSearchInput 单测负责）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const { mockNavigate, mockOpenKLine, mockDone } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockOpenKLine: vi.fn(),
  mockDone: vi.fn(),
}))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

// mutation 反证用：若命中仍走 openKLine，本文件的 navigate 断言会红。
vi.mock('@/features/stock/charts/klineOverlayStore', () => ({
  openKLine: (...args: unknown[]) => mockOpenKLine(...args),
}))

vi.mock('@/shared/ui/StockSearchInput', () => ({
  StockSearchInput: ({
    value,
    onSelect,
  }: {
    value: string
    onSelect: (code: string, item?: { name?: string }) => void
  }) => (
    <button type="button" data-value={value} onClick={() => onSelect('600519', { name: '贵州茅台' })}>
      选中股票
    </button>
  ),
}))

import { GlobalStockSearch, MobileSearch, SearchCluster } from '@/app/AppShell'

beforeEach(() => vi.clearAllMocks())

describe('GlobalStockSearch · 命中跳个股研究页', () => {
  it('navigate 到 /stock/research 且 search.code 等于输入代码（mutation 反证：若仍是 openKLine 则红）', () => {
    render(<GlobalStockSearch />)
    fireEvent.click(screen.getByRole('button', { name: '选中股票' }))

    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/stock/research',
      search: { code: '600519' },
    })
    expect(mockOpenKLine).not.toHaveBeenCalled()
  })

  it('命中后调用 onDone（窄屏浮层据此关闭），输入框 value 清空', () => {
    render(<GlobalStockSearch onDone={mockDone} />)
    const btn = screen.getByRole('button', { name: '选中股票' }) as HTMLButtonElement
    expect(btn.getAttribute('data-value')).toBe('')
    fireEvent.click(btn)
    expect(btn.getAttribute('data-value')).toBe('')
    expect(mockDone).toHaveBeenCalledTimes(1)
  })
})

describe('SearchCluster / MobileSearch · 窄屏搜索入口', () => {
  it('SearchCluster 同时含功能搜索与股票搜索，窄屏用 w-full 复用同一份', () => {
    render(<SearchCluster mobile />)
    expect(screen.getByRole('combobox', { name: '功能搜索' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '选中股票' })).toBeTruthy()
  })

  it('搜索图标按钮 md:hidden，点击展开浮层，Esc 可关', () => {
    render(<MobileSearch />)
    const btn = screen.getByRole('button', { name: '搜索' })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
    expect((btn.parentElement as HTMLElement).className).toContain('md:hidden')

    fireEvent.click(btn)
    expect(btn.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByRole('dialog', { name: '搜索' })).toBeTruthy()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: '搜索' })).toBeNull()
  })

  it('窄屏浮层内选中股票 → navigate 到研究页并自动关闭浮层', () => {
    render(<MobileSearch />)
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    fireEvent.click(screen.getByRole('button', { name: '选中股票' }))

    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/stock/research',
      search: { code: '600519' },
    })
    expect(screen.queryByRole('dialog', { name: '搜索' })).toBeNull()
  })
})

describe('AppShell 源码静态守卫', () => {
  const shell = () => readFileSync(resolve(process.cwd(), 'src/app/AppShell.tsx'), 'utf8')

  it('搜索命中走 navigate 到研究页、setCode 清空，且不再 import/调用 openKLine', () => {
    const s = shell()
    expect(s).toContain("navigate({ to: '/stock/research', search: { code: next } })")
    expect(s).toContain("setCode('')")
    expect(s).not.toMatch(/import \{ openKLine \}/)
    expect(s).not.toContain('openKLine(next')
  })

  it('保留 ThemeToggle 顺序、GlobalKLineOverlay 挂载与 md:hidden 搜索入口', () => {
    const s = shell()
    expect(s.indexOf('<ThemeToggle')).toBeGreaterThan(-1)
    expect(s.indexOf('<ThemeToggle')).toBeLessThan(s.indexOf('退出登录'))
    expect(s).toContain('<GlobalKLineOverlay />')
    expect(s).toContain('aria-label="搜索"')
    expect(s).toContain('md:hidden')
  })
})
