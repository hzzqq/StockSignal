import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { CatalogView } from './CatalogView'
import { V1_PAGES } from './v1Pages.generated'
import { mappingOf } from './v2Mapping'

// CatalogView 用 Link 做内部跳转，测试不需要真实路由：透传 children 为 <a>。
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, className }: { children?: ReactElement | string; className?: string }) => (
    <a className={className}>{children}</a>
  ),
}))

beforeEach(() => localStorage.clear())
afterEach(() => localStorage.clear())

describe('CatalogView · v1 功能全景 · 诚实三档 + 搜索/筛选', () => {
  it('渲染标题、五档 Stat 标签与诚实声明「列出 ≠ 已实现」', () => {
    render(<CatalogView />)
    expect(screen.getByText('v1 功能全景')).toBeTruthy()
    expect(screen.getByText('v1 功能页总数')).toBeTruthy()
    expect(screen.getByText('v2 已实现')).toBeTruthy()
    expect(screen.getByText('关联只读数据')).toBeTruthy()
    // 「v1 保留」「待迁移」既是 Stat 标签也是筛选按钮文字，去歧义用 getAllByText
    expect(screen.getAllByText('v1 保留').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('待迁移').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/列出 ≠ 已实现/)).toBeTruthy()
  })

  it('搜索无匹配 → 诚实空态「没有匹配的功能页。」', () => {
    render(<CatalogView />)
    const search = screen.getByLabelText('搜索功能')
    fireEvent.change(search, { target: { value: 'zzzqqq' } })
    expect(screen.getByText('没有匹配的功能页。')).toBeTruthy()
  })

  it('状态筛选联动：native 命中、v1-only 下消失（用真实生成数据驱动）', async () => {
    const nativePage = V1_PAGES.find((p) => mappingOf(p).status === 'native')
    // 生成数据必须至少含一个 native 页（与四档口径 63 native 一致），否则此断言即失效。
    expect(nativePage).toBeTruthy()

    render(<CatalogView />)
    const search = screen.getByLabelText('搜索功能')
    fireEvent.change(search, { target: { value: nativePage!.name } })
    fireEvent.click(screen.getByRole('button', { name: '已实现' }))
    await waitFor(() => {
      expect(screen.getByText(nativePage!.name)).toBeTruthy()
    })

    // 切到「待迁移」：native 页不应再出现 → 空态
    fireEvent.click(screen.getByRole('button', { name: '待迁移' }))
    await waitFor(() => {
      expect(screen.queryByText(nativePage!.name)).toBeNull()
    })
    expect(screen.getByText('没有匹配的功能页。')).toBeTruthy()
  })

  it('筛选按钮 aria-pressed 随点击切换', () => {
    render(<CatalogView />)
    const nativeBtn = screen.getByRole('button', { name: '已实现' })
    expect(nativeBtn.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(nativeBtn)
    expect(nativeBtn.getAttribute('aria-pressed')).toBe('true')
  })
})
