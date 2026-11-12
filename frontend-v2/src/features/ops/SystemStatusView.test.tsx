import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SystemStatusView } from './SystemStatusView'
import type { P1SyncStatus, BacktestRuns, DataRefreshState } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getP1SyncStatus: vi.fn(),
  getBacktestRuns: vi.fn(),
  getDataRefreshState: vi.fn(),
}))
import { getP1SyncStatus, getBacktestRuns, getDataRefreshState } from '@/api/read'
const syncMock = vi.mocked(getP1SyncStatus)
const runsMock = vi.mocked(getBacktestRuns)
const refreshMock = vi.mocked(getDataRefreshState)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const syncOk = {
  run_at: '2026-03-01 08:00',
  ok: true,
  mode: 'daily',
  interval_minutes: 60,
  counts: { copy: 2, unchanged: 3 },
  health: {
    status: 'ok',
    message: '全部模型信号新鲜',
    age_days: 1,
    rows: [
      {
        file: 'signal_h10.json', model_key: 'h10', latest_date: '2026-10-16',
        age_days: 1, structural_ok: true, freshness_ok: true,
      },
    ],
  },
  // 真实文件含绝对路径；后端已剔除，前端 catchall 收到也绝不渲染
  target_dir: 'E:/project/sj/data/P1/processed/signals',
} as unknown as P1SyncStatus

const runsOk = {
  runs: [{
    run_id: 'r1', created_at: '2026-03-01', status: 'done',
    summary: {
      ticker: '600000', strategy: 'momentum',
      total_return_pct: -12.5, max_drawdown_pct: -8.25, sharpe_ratio: -0.85,
      trade_count: 12,
    },
  }],
} as BacktestRuns

const refreshOk = {
  attempts_today: 2, last_run_date: '2026-03-01', last_result: 'ok',
  finished_at: '2026-03-01 15:30', last_csv_date: '2026-02-28', detail: 'refresh ok',
} as DataRefreshState

beforeEach(() => {
  syncMock.mockReset().mockResolvedValue(syncOk)
  runsMock.mockReset().mockResolvedValue(runsOk)
  refreshMock.mockReset().mockResolvedValue(refreshOk)
})

describe('SystemStatusView · 数据与运维状态 · 三源独立 + 负收益口径', () => {
  it('三源成功 → 各自独立渲染（同步/回测/刷新）', async () => {
    renderWithClient(<SystemStatusView />)
    // 标题常驻，必须 await 仅数据态才出现的元素作为加载完成信号
    expect(await screen.findByText('2026-03-01 08:00')).toBeTruthy()
    expect(screen.getByText('P1 信号同步')).toBeTruthy()
    expect(screen.getByText('600000')).toBeTruthy()
    expect(screen.getByText('refresh ok')).toBeTruthy()
  })

  it('任一源失败不影响另两块（不连带整页空白）', async () => {
    syncMock.mockRejectedValue(new Error('同步状态挂了'))
    renderWithClient(<SystemStatusView />)
    await expect(screen.findByText('同步状态挂了')).resolves.toBeTruthy()
    // 另两块照常渲染
    expect(screen.getByText('600000')).toBeTruthy()
    expect(screen.getByText('refresh ok')).toBeTruthy()
  })

  it('负收益 / 负回撤 / 负 Sharpe 原样带符号，不取绝对值、不包装成领先', async () => {
    renderWithClient(<SystemStatusView />)
    expect(await screen.findByText('-12.50')).toBeTruthy()
    expect(screen.getByText('-8.25')).toBeTruthy()
    expect(screen.getByText('-0.85')).toBeTruthy()
    expect(screen.queryByText('+12.50')).toBeNull()
    expect(screen.queryByText('12.50')).toBeNull()
    expect(screen.getByText(/负收益与负 Sharpe 如实保留、未取绝对值/)).toBeTruthy()
  })

  it('字段缺失 → 一律「—」，不补零', async () => {
    runsMock.mockResolvedValue({
      runs: [{ run_id: 'r2', summary: {} }],
    } as BacktestRuns)
    refreshMock.mockResolvedValue({} as DataRefreshState)
    renderWithClient(<SystemStatusView />)
    expect(await screen.findByText('原始文件未提供明细')).toBeTruthy()
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4)
    expect(screen.queryByText('0.00')).toBeNull()
  })

  it('绝对路径类字段绝不展示（后端脱敏 + 前端只渲染 schema 显式字段）', async () => {
    renderWithClient(<SystemStatusView />)
    expect(await screen.findByText('全部模型信号新鲜')).toBeTruthy()
    expect(screen.queryByText(/E:\/project/)).toBeNull()
    expect(screen.queryByText(/processed\/signals/)).toBeNull()
    expect(screen.getByText(/绝对路径类字段已由后端递归脱敏，本页不展示/)).toBeTruthy()
  })

  it('健康检查逐模型明细：达标 / 超 SLA / 结构校验如实区分', async () => {
    syncMock.mockResolvedValue({
      ...syncOk,
      health: {
        status: 'warn', message: '部分信号超 SLA', age_days: 10,
        rows: [
          { file: 'a.json', model_key: 'h10', latest_date: '2026-10-16', age_days: 1, structural_ok: true, freshness_ok: true },
          { file: 'b.json', model_key: 'h5', latest_date: '2026-08-01', age_days: 10, structural_ok: false, freshness_ok: false },
        ],
      },
    } as unknown as P1SyncStatus)
    renderWithClient(<SystemStatusView />)
    expect(await screen.findByText('达标')).toBeTruthy()
    expect(screen.getByText('超 SLA')).toBeTruthy()
    expect(screen.getByText('未通过')).toBeTruthy()
  })

  it('三源全空 → 3 个独立诚实空态，不互相掩盖', async () => {
    syncMock.mockResolvedValue(null as unknown as P1SyncStatus)
    runsMock.mockResolvedValue({ runs: [] } as BacktestRuns)
    refreshMock.mockResolvedValue(null as unknown as DataRefreshState)
    renderWithClient(<SystemStatusView />)
    await expect(screen.findByText('无同步状态记录')).resolves.toBeTruthy()
    expect(screen.getByText('无回测运行记录')).toBeTruthy()
    expect(screen.getByText('无刷新状态记录')).toBeTruthy()
  })
})
