import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LoginWelcome } from './LoginWelcome'

describe('LoginWelcome · 登录欢迎门禁 · 静态品牌 + 演示账号 + 回调', () => {
  it('渲染品牌主标题与平台名（无未经验证的数字）', () => {
    render(<LoginWelcome onLogin={() => {}} />)
    expect(screen.getByText(/放心交给 StockSignal/)).toBeTruthy()
    expect(screen.getByText('StockSignal')).toBeTruthy()
    expect(screen.getByText('A股事件驱动投资分析平台')).toBeTruthy()
  })

  it('展示真实可用的演示账号', () => {
    render(<LoginWelcome onLogin={() => {}} />)
    expect(screen.getByText(/默认演示账号：demo \/ Demo@123/)).toBeTruthy()
  })

  it('底部脚注：仅供学习研究，不构成投资建议', () => {
    render(<LoginWelcome onLogin={() => {}} />)
    expect(screen.getByText(/仅供学习与研究所用，不构成投资建议/)).toBeTruthy()
  })

  it('点击「去登录」→ 触发 onLogin 回调一次', () => {
    const onLogin = vi.fn()
    render(<LoginWelcome onLogin={onLogin} />)
    fireEvent.click(screen.getByText(/去登录/))
    expect(onLogin).toHaveBeenCalledTimes(1)
  })
})
