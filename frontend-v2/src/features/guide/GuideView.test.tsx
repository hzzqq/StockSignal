import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { GuideView } from './GuideView'

// GuideView 仅用 Link 做内部跳转，测试中不需要真实路由：透传 children。
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: ReactElement | string }) => <span>{children}</span>,
}))

const LS_KEY = 'ss_guide_steps'

beforeEach(() => {
  localStorage.clear()
})
afterEach(() => {
  localStorage.clear()
})

function renderView() {
  return render(<GuideView />)
}

describe('GuideView · 新手教程 · 静态引导 + localStorage 进度 + FAQ 筛选', () => {
  it('渲染全部引导区块（无动态行情数字）', () => {
    renderView()
    expect(screen.getByText('新手教程')).toBeTruthy()
    expect(screen.getByText('四步上手')).toBeTruthy()
    expect(screen.getByText('差异化主线速览')).toBeTruthy()
    expect(screen.getByText('模块导览')).toBeTruthy()
    expect(screen.getByText('术语表')).toBeTruthy()
    expect(screen.getByText('常见误区')).toBeTruthy()
    expect(screen.getByText('常见问题')).toBeTruthy()
    // 诚实说明：进度只写本浏览器 localStorage
    expect(screen.getByText(/进度保存在此浏览器/)).toBeTruthy()
  })

  it('初始进度 0/4 · 0%（无 localStorage）', () => {
    renderView()
    expect(screen.getByText(/0 \/ 4/)).toBeTruthy()
    expect(screen.getByText(/0%/)).toBeTruthy()
  })

  it('勾选一项 → 进度 1/4 · 25% 且写回 localStorage', async () => {
    renderView()
    const box = screen.getByLabelText('看一遍今日决策面板') as HTMLInputElement
    expect(box.checked).toBe(false)
    fireEvent.click(box)
    await waitFor(() => {
      expect(screen.getByText(/1 \/ 4/)).toBeTruthy()
      expect(screen.getByText(/25%/)).toBeTruthy()
    })
    const stored = JSON.parse(localStorage.getItem(LS_KEY) ?? '[]') as unknown[]
    expect(stored).toContain('decision')
  })

  it('localStorage 损坏 JSON → 回落空进度（不崩溃、不谎报）', () => {
    localStorage.setItem(LS_KEY, 'not-json{')
    renderView()
    expect(screen.getByText(/0 \/ 4/)).toBeTruthy()
    const box = screen.getByLabelText('看一遍今日决策面板') as HTMLInputElement
    expect(box.checked).toBe(false)
  })

  it('FAQ 搜索命中 → 仅保留匹配项', () => {
    renderView()
    const input = screen.getByLabelText('搜索常见问题')
    fireEvent.change(input, { target: { value: '同步' } })
    expect(screen.getByText('设置会同步到我的账号吗？')).toBeTruthy()
    expect(screen.queryByText('v2 和 v1 是什么关系？')).toBeNull()
  })

  it('FAQ 搜索无命中 → 诚实空态', () => {
    renderView()
    const input = screen.getByLabelText('搜索常见问题')
    fireEvent.change(input, { target: { value: 'zzzqqq' } })
    expect(screen.getByText('没有匹配的问题，请换个关键词。')).toBeTruthy()
    expect(screen.queryByText('设置会同步到我的账号吗？')).toBeNull()
  })
})
