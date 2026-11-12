import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DiagnosticsView } from './DiagnosticsView'
import type { Diagnostics } from '@/api/schemas/diagnostics'

vi.mock('@/api/diagnostics', () => ({
  getDiagnostics: vi.fn(),
  probeEndpoints: vi.fn(),
  mocksEnabled: vi.fn(() => false),
}))
import { getDiagnostics, probeEndpoints, mocksEnabled } from '@/api/diagnostics'
const diagMock = vi.mocked(getDiagnostics)
const probeMock = vi.mocked(probeEndpoints)
const mocksMock = vi.mocked(mocksEnabled)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

function makeDiag(overrides: Record<string, unknown> = {}): Diagnostics {
  return {
    sources: {
      available: true, summary: '4/4 可用', checked_at: '2026-03-01 08:00',
      items: [{ key: 'akshare', label: 'akshare', ok: true, detail: 'installed', tables: { daily: 5000 } }],
      reason: null,
    },
    freshness: {
      available: true,
      rows: [
        { key: 'p1', name: 'P1 信号', as_of: '2026-10-16', lag_days: 2, status: 'ok' },
        { key: 'breadth', name: '广度', as_of: '2026-09-01', lag_days: 10, status: 'stale' },
        { key: 'x', name: '未知源', as_of: null, lag_days: null, status: 'unknown' },
      ],
      reason: null,
    },
    endpoints: [
      {
        path: '/api/v2/read/daily-snapshot', needs_params: false,
        probe_path: '/api/v2/read/daily-snapshot', required_query: [], sample_query: null,
      },
    ],
    probe: null,
    note: '检测结论仅代表当前时刻连通性',
    ...overrides,
  } as unknown as Diagnostics
}

beforeEach(() => {
  diagMock.mockReset().mockResolvedValue(makeDiag())
  probeMock.mockReset().mockResolvedValue([])
  mocksMock.mockReset().mockReturnValue(false)
})

describe('DiagnosticsView · 数据源与接口检测 · 零网络 + 诚实降级', () => {
  it('默认零网络：probe=false 查询，不发任何端点探测，probe=null 显「尚未探测」', async () => {
    renderWithClient(<DiagnosticsView />)
    expect(await screen.findByText('数据源与接口检测')).toBeTruthy()
    expect(await screen.findByText('尚未探测（默认零网络）。')).toBeTruthy()
    expect(diagMock).toHaveBeenCalledWith(false)
    expect(probeMock).not.toHaveBeenCalled()
    expect(screen.getByText('开始真实网络探测')).toBeTruthy()
  })

  it('loading / error / 空数据 四态', async () => {
    const { unmount } = renderWithClient(<DiagnosticsView />)
    expect(screen.getByText('加载中…')).toBeTruthy()
    unmount()

    diagMock.mockRejectedValue(new Error('诊断数据加载失败'))
    const r2 = renderWithClient(<DiagnosticsView />)
    await expect(screen.findByText('诊断数据加载失败')).resolves.toBeTruthy()
    r2.unmount()

    diagMock.mockResolvedValue(null as unknown as Diagnostics)
    renderWithClient(<DiagnosticsView />)
    await expect(screen.findByText('无检测数据')).resolves.toBeTruthy()
  })

  it('MSW 环境 → 显式警示「全部检测结果均为模拟数据」，不冒充真实连通性', async () => {
    mocksMock.mockReturnValue(true)
    renderWithClient(<DiagnosticsView />)
    expect(await screen.findByText(/全部检测结果（含四源网络探测与接口检测）均为模拟数据/)).toBeTruthy()
    expect(screen.getByText(/既不代表真实后端连通性，也不代表数据源通断/)).toBeTruthy()
    // 警示横幅常驻（在 QueryState 外），必须 await 数据态 Card 标题作为加载完成信号
    expect(await screen.findByText('四源网络探测（模拟数据）')).toBeTruthy()
  })

  it('未探测时「接口连通」显「未检测」，绝不补 0 冒充「0 个成功」', async () => {
    renderWithClient(<DiagnosticsView />)
    expect(await screen.findByText('未检测')).toBeTruthy()
    expect(screen.queryByText('0/0')).toBeNull()
    expect(screen.getByText('尚未检测。点击「开始检测」对 1 个端点发起真实请求。')).toBeTruthy()
  })

  it('probe.available=false → 独立显示 reason，绝不包装成「全部正常」', async () => {
    diagMock.mockResolvedValue(makeDiag({
      probe: { available: false, levels: [], reason: '四源探测脚本不可用' },
    }))
    renderWithClient(<DiagnosticsView />)
    await expect(screen.findByText('探测不可用：四源探测脚本不可用')).resolves.toBeTruthy()
    expect(screen.queryByText('通')).toBeNull()
  })

  it('probe.levels 为空 → 「探测未返回任何结果。」，不伪造四源状态', async () => {
    diagMock.mockResolvedValue(makeDiag({ probe: { available: true, levels: [], reason: null } }))
    renderWithClient(<DiagnosticsView />)
    await expect(screen.findByText('探测未返回任何结果。')).resolves.toBeTruthy()
  })

  it('sources / freshness 各自 available=false → 分区独立降级，其余分区照常', async () => {
    diagMock.mockResolvedValue(makeDiag({
      sources: { available: false, summary: null, checked_at: null, items: [], reason: '依赖模块缺失' },
      freshness: { available: false, rows: [], reason: 'health_rows 异常' },
    }))
    renderWithClient(<DiagnosticsView />)
    await expect(screen.findByText('检测不可用：依赖模块缺失')).resolves.toBeTruthy()
    expect(screen.getByText('检测不可用：health_rows 异常')).toBeTruthy()
    // 接口检测分区仍照常渲染
    expect(screen.getByText('只读端点连通性')).toBeTruthy()
  })

  it('freshness 状态文字如实：ok→正常 / stale→滞后 / unknown→未知；缺失 as_of 显「—」', async () => {
    renderWithClient(<DiagnosticsView />)
    expect(await screen.findByText('各数据源时效')).toBeTruthy()
    expect(screen.getByText('正常')).toBeTruthy()
    expect(screen.getByText('滞后')).toBeTruthy()
    expect(screen.getByText('未知')).toBeTruthy()
    expect(screen.getByText('2026-10-16')).toBeTruthy()
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
  })

  it('点击「开始检测」→ 对可探测端点发起真实 GET 并如实记录结果', async () => {
    probeMock.mockResolvedValue([{
      path: '/api/v2/read/daily-snapshot', httpStatus: 200, envelopeStatus: 'ok',
      ok: true, latencyMs: 42, detail: '正常',
    }])
    renderWithClient(<DiagnosticsView />)
    expect(await screen.findByText('开始检测')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '开始检测' }))
    expect(await screen.findByText('42 ms')).toBeTruthy()
    expect(probeMock).toHaveBeenCalledWith(['/api/v2/read/daily-snapshot'])
    expect(screen.getByText('1/1')).toBeTruthy()
    // 「正常」同时出现在时效表与探测结果表 → 至少 2 处
    expect(screen.getAllByText('正常').length).toBeGreaterThanOrEqual(2)
  })
})
