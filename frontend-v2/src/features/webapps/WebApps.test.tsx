import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WebApps } from './WebApps'

vi.mock('@/api/read', () => ({
  getWebApps: vi.fn(),
}))
import { getWebApps } from '@/api/read'
const mocked = vi.mocked(getWebApps)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = [
  { dir: 'app1', title: '作品A', desc: '描述A', entry: 'index.html', version: '1.0', added: '2026-01-01' },
  { dir: 'app2', title: '作品B', desc: '描述B', entry: 'index.html', version: '2.1', added: '2026-02-01' },
]

beforeEach(() => {
  mocked.mockReset()
})

describe('WebApps 四态', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<WebApps />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('作品集加载失败'))
    renderWithClient(<WebApps />)
    await expect(screen.findByText('作品集加载失败')).resolves.toBeTruthy()
  })

  it('ok 渲染作品卡片（标题/描述/版本·日期）', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<WebApps />)
    // 标题始终存在，改用数据态才出现的作品标题作为加载完成信号
    expect(await screen.findByText('作品A')).toBeTruthy()
    expect(screen.getByText('网页作品集')).toBeTruthy()
    expect(screen.getByText('描述A')).toBeTruthy()
    expect(screen.getByText('v1.0 · 2026-01-01')).toBeTruthy()
    expect(screen.getByText('作品B')).toBeTruthy()
  })

  it('空数组 → 暂无作品（诚实空态）', async () => {
    mocked.mockResolvedValue([])
    renderWithClient(<WebApps />)
    await expect(screen.findByText('暂无作品')).resolves.toBeTruthy()
    expect(screen.getByText(/webapps\//)).toBeTruthy()
  })
})
