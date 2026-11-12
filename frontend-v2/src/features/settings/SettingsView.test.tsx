import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SettingsView } from './SettingsView'
import { clearAuth } from '@/app/guards'
import { mocksEnabled } from '@/api/diagnostics'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: unknown }) => <span>{String(children)}</span>,
  useNavigate: () => mockNavigate,
}))
vi.mock('@/app/guards', () => ({ clearAuth: vi.fn() }))
vi.mock('@/api/diagnostics', () => ({ mocksEnabled: vi.fn() }))

const mClear = vi.mocked(clearAuth)
const mMocked = vi.mocked(mocksEnabled)

beforeEach(() => {
  mClear.mockReset()
  mMocked.mockReset()
  mockNavigate.mockReset()
  localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

describe('SettingsView · 设置 · 本地偏好真实生效 + 连通性诚实披露 + 退出', () => {
  it('渲染标题与「本机偏好」副标题', () => {
    mMocked.mockReturnValue(false)
    render(<SettingsView />)
    expect(screen.getByText('设置')).toBeTruthy()
    expect(screen.getByText(/本机偏好 · 保存在此浏览器/)).toBeTruthy()
  })

  it('表格密度：初始「标准」选中；切「紧凑」→ 写回 localStorage + aria-checked + 文案', () => {
    mMocked.mockReturnValue(false)
    render(<SettingsView />)
    expect((screen.getByRole('radio', { name: '标准' }) as HTMLButtonElement).getAttribute('aria-checked')).toBe('true')
    fireEvent.click(screen.getByRole('radio', { name: '紧凑' }))
    expect((screen.getByRole('radio', { name: '紧凑' }) as HTMLButtonElement).getAttribute('aria-checked')).toBe('true')
    expect(localStorage.getItem('ss_density')).toBe('compact')
    expect(screen.getByText(/（紧凑）/)).toBeTruthy()
  })

  it('v1 服务地址：修改后保存 → 「已保存」回显 + 持久化到 localStorage', () => {
    mMocked.mockReturnValue(false)
    render(<SettingsView />)
    const input = screen.getByLabelText('v1 服务地址') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'http://example.com:8501' } })
    fireEvent.click(screen.getByText('保存'))
    expect(screen.getByText('已保存：http://example.com:8501')).toBeTruthy()
    expect(localStorage.getItem('ss_v1_base')).toBe('http://example.com:8501')
  })

  it('数据源当前模式：真实后端（mocksEnabled=false）', () => {
    mMocked.mockReturnValue(false)
    render(<SettingsView />)
    expect(screen.getByText('真实后端')).toBeTruthy()
    expect(screen.getByText(/请求经 Vite 代理发往后端/)).toBeTruthy()
  })

  it('数据源当前模式：开发模拟数据（mocksEnabled=true）明确标注非真实', () => {
    mMocked.mockReturnValue(true)
    render(<SettingsView />)
    expect(screen.getByText('开发模拟数据（MSW）')).toBeTruthy()
    expect(screen.getByText(/页面上的行情与检测结果可能是模拟响应/)).toBeTruthy()
  })

  it('连通性检测成功 → HTTP 200 + 「后端健康检查通过」如实披露', async () => {
    mMocked.mockReturnValue(false)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200, ok: true } as never))
    render(<SettingsView />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => expect(screen.getByText(/HTTP 200/)).toBeTruthy())
    expect(screen.getByText(/后端健康检查通过/)).toBeTruthy()
  })

  it('连通性检测失败 → 诚实披露「无法连接」错误原因（不包装成成功）', async () => {
    mMocked.mockReturnValue(false)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('conn refused')))
    render(<SettingsView />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => expect(screen.getByText(/无法连接：conn refused/)).toBeTruthy())
    expect(screen.getByText(/HTTP —/)).toBeTruthy()
  })

  it('退出登录 → clearAuth + navigate 到 /login（保留来源）', () => {
    mMocked.mockReturnValue(false)
    render(<SettingsView />)
    fireEvent.click(screen.getByText('退出登录'))
    expect(mClear).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/login', search: { from: '/' } })
  })

  it('关于区块：v1 登记数（74，磁盘实扫）+ 构建模式如实渲染', () => {
    mMocked.mockReturnValue(false)
    render(<SettingsView />)
    expect(screen.getByText(/v1 功能页登记数/)).toBeTruthy()
    expect(screen.getByText('74')).toBeTruthy()
    expect(screen.getByText(/构建模式/)).toBeTruthy()
    expect(screen.getByText(String(import.meta.env.MODE))).toBeTruthy()
  })
})
