import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { BreadthAnalytics } from '@/api/schemas/read'
import { InflectionScan } from './InflectionScan'

vi.mock('@/api/read', () => ({
  getBreadthAnalytics: vi.fn(),
}))
import { getBreadthAnalytics } from '@/api/read'
const mocked = vi.mocked(getBreadthAnalytics)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

// 仅填组件实际读取的字段（sections.inflection / reliable_labels / offline_missing /
// data_as_of / note）；其余字段以类型断言绕过（esbuild 运行期不校验，tsc 用 as unknown as）。
const okNoDims = {
  data_as_of: null,
  window: 250,
  reliable_dims: [],
  reliable_labels: {},
  offline_missing: {},
  note: '',
  sections: { inflection: { available: true, dims: [], events: [] } },
} as unknown as BreadthAnalytics

beforeEach(() => {
  mocked.mockReset()
})

describe('InflectionScan 四态 + 诚实降级', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<InflectionScan />)
    expect(screen.getByText('加载拐点扫描结果…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('拐点扫描结果加载失败'))
    renderWithClient(<InflectionScan />)
    await expect(screen.findByText('拐点扫描结果加载失败')).resolves.toBeTruthy()
  })

  it('空数据 → 诚实空态「暂无拐点扫描结果」', async () => {
    mocked.mockResolvedValue(null as unknown as BreadthAnalytics)
    renderWithClient(<InflectionScan />)
    await expect(screen.findByText('暂无拐点扫描结果')).resolves.toBeTruthy()
  })

  it('数据到位但无维度 → 诚实空态「无可用广度维度生成拐点扫描」', async () => {
    mocked.mockResolvedValue(okNoDims)
    renderWithClient(<InflectionScan />)
    // 标题常驻；改用数据态才出现的维度空态作为加载完成信号
    expect(await screen.findByText('无可用广度维度生成拐点扫描')).toBeTruthy()
  })
})
