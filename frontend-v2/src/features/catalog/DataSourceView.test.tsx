import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { DataSourceView } from './DataSourceView'
import { useDiagnostics } from '@/lib/queries'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: ReactElement | string }) => <span>{children}</span>,
}))
vi.mock('@/lib/queries', () => ({ useDiagnostics: vi.fn() }))

const mDiag = vi.mocked(useDiagnostics)

const GOOD_ENDPOINTS = [
  { path: '/read/x', needs_params: false, sample_query: '' },
  { path: '/read/y', needs_params: true, sample_query: 'code=600519' },
  { path: '/read/z<id>', needs_params: false, sample_query: '' },
]

beforeEach(() => {
  mDiag.mockReset()
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ status: 'ok', data: [] }) }),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('DataSourceView · 只读端点数据浏览器 · 诚实红线 + 四态', () => {
  it('渲染标题与返回功能全景入口', () => {
    mDiag.mockReturnValue({ data: { endpoints: GOOD_ENDPOINTS }, isLoading: false, isError: false, error: null } as never)
    render(<DataSourceView />)
    expect(screen.getByText('只读端点数据浏览器')).toBeTruthy()
    expect(screen.getByText('返回功能全景 →')).toBeTruthy()
  })

  it('诊断失败 → ErrorState（不编造端点）', () => {
    mDiag.mockReturnValue({ data: null, isLoading: false, isError: true, error: new Error('boom') } as never)
    render(<DataSourceView />)
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.getByText('boom')).toBeTruthy()
  })

  it('含路径参数的端点被如实排除（< 端点不进下拉）', () => {
    mDiag.mockReturnValue({ data: { endpoints: GOOD_ENDPOINTS }, isLoading: false, isError: false, error: null } as never)
    render(<DataSourceView />)
    expect(screen.getByRole('option', { name: '/read/x' })).toBeTruthy()
    expect(screen.getByRole('option', { name: '/read/y' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: '/read/z<id>' })).toBeNull()
  })

  it('选择端点并读取成功 → 渲染真实数据表 + HTTP 200', async () => {
    mDiag.mockReturnValue({ data: { endpoints: GOOD_ENDPOINTS }, isLoading: false, isError: false, error: null } as never)
    vi.mocked(fetch).mockResolvedValue({
      status: 200, ok: true, json: async () => ({ status: 'ok', data: [{ a: 1, b: 2 }] }),
    } as never)
    render(<DataSourceView />)
    const select = screen.getByLabelText('只读端点') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '/read/x' } })
    await waitFor(() => expect(screen.getByText('a')).toBeTruthy())
    expect(screen.getByText('b')).toBeTruthy()
    expect(screen.getByText(/HTTP 200/)).toBeTruthy()
  })

  it('读取失败 → 诚实披露错误（不包装成成功）', async () => {
    mDiag.mockReturnValue({ data: { endpoints: GOOD_ENDPOINTS }, isLoading: false, isError: false, error: null } as never)
    vi.mocked(fetch).mockRejectedValue(new Error('network down'))
    render(<DataSourceView />)
    const select = screen.getByLabelText('只读端点') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '/read/x' } })
    await waitFor(() => expect(screen.getByText(/读取失败/)).toBeTruthy())
  })

  it('需参数端点 → 查询框示例占位 + 提示文案', () => {
    mDiag.mockReturnValue({ data: { endpoints: GOOD_ENDPOINTS }, isLoading: false, isError: false, error: null } as never)
    render(<DataSourceView />)
    const select = screen.getByLabelText('只读端点') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '/read/y' } })
    expect(screen.getByPlaceholderText('code=600519')).toBeTruthy()
    expect(screen.getByText(/示例参数仅用于演示/)).toBeTruthy()
  })
})
