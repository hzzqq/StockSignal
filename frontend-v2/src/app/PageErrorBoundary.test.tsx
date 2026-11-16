import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { PageErrorBoundary } from './PageErrorBoundary'

afterEach(() => vi.restoreAllMocks())

describe('PageErrorBoundary · 页面渲染异常不白屏', () => {
  it('正常子树原样渲染，不多画任何东西', () => {
    render(<PageErrorBoundary><p>正常内容</p></PageErrorBoundary>)
    expect(screen.getByText('正常内容')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('子树抛错 → 显示原始错误与重试入口，绝不整页空白', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    function Boom(): ReactNode {
      throw new Error('消息气泡炸了')
    }
    render(<PageErrorBoundary><Boom /></PageErrorBoundary>)
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('页面渲染失败')
    expect(alert.textContent).toContain('消息气泡炸了')
    expect(screen.getByRole('button', { name: /重试渲染/ })).toBeTruthy()
  })
})
