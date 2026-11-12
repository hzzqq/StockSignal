import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PredictionLogView } from './PredictionLogView'
import type { PredictionLogRow } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({ getPredictionLog: vi.fn() }))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
import { getPredictionLog } from '@/api/read'
const mocked = vi.mocked(getPredictionLog)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

/** hit=null 表示「尚未兑现」，既不是未命中也不是 0。 */
const mixed: PredictionLogRow[] = [
  { date: '2026-03-01', temp: 50, bias: '偏多', pct: 60, hit: null },
  { date: '2026-03-02', temp: 52, bias: '偏空', pct: 40, hit: true },
  { date: '2026-03-03', temp: 55, bias: '偏多', pct: 65, hit: false },
  { date: '2026-03-04', temp: 58, bias: '偏多', pct: 70, hit: null },
]

beforeEach(() => {
  mocked.mockReset().mockResolvedValue(mixed)
})

describe('PredictionLogView · 预测校准日志 · 命中率口径诚实守卫', () => {
  it('loading → 加载中…', () => {
    mocked.mockReturnValue(new Promise<PredictionLogRow[]>(() => {}))
    renderWithClient(<PredictionLogView />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error → 原样带出错误，不吞异常', async () => {
    mocked.mockRejectedValue(new Error('日志加载失败'))
    renderWithClient(<PredictionLogView />)
    await expect(screen.findByText('日志加载失败')).resolves.toBeTruthy()
  })

  it('空日志 → 诚实空态「暂无预测记录」+ 未填充 hint', async () => {
    mocked.mockResolvedValue([])
    renderWithClient(<PredictionLogView />)
    await expect(screen.findByText('暂无预测记录')).resolves.toBeTruthy()
    expect(screen.getByText('数据文件缺失或日志为空，未做任何填充')).toBeTruthy()
  })

  it('命中率分母只算 hit 为布尔值的已兑现样本：4 条日志 / 2 已兑现 / 1 命中 → 50.0%', async () => {
    renderWithClient(<PredictionLogView />)
    expect(await screen.findByText('口径说明')).toBeTruthy()
    const rate = screen.getByText('命中率').parentElement
    expect(rate?.textContent).toContain('50.0%')
    expect(rate?.textContent).toContain('分母 2 条')
    // 未兑现的 2 条既不计分子也不计分母，绝不按「未命中」拉低命中率
    expect(rate?.textContent).not.toContain('25.0%')
    expect(screen.getByText('日志条数').parentElement?.textContent).toContain('4')
    expect(screen.getByText('已兑现').parentElement?.textContent).toContain('2')
    // 「命中」在 Stat label 与明细表「命中/未命中」列各出现一次 → 取 Stat 那个
    expect(screen.getAllByText('命中')[0].parentElement?.textContent).toContain('1')
  })

  it('全部未兑现（无可统计样本）→ 命中率显「—」+「无可统计样本」，绝不补 0.0%', async () => {
    mocked.mockResolvedValue([
      { date: '2026-03-01', temp: 50, hit: null },
      { date: '2026-03-02', temp: 51, hit: null },
    ])
    renderWithClient(<PredictionLogView />)
    expect(await screen.findByText('无可统计样本')).toBeTruthy()
    expect(screen.getByText('命中率').parentElement?.textContent).toContain('—')
    expect(screen.queryByText(/0\.0%/)).toBeNull()
    expect(screen.queryByText(/100\.0%/)).toBeNull()
  })

  it('口径说明与最新一条如实带出，不把历史自评包装成未来预测', async () => {
    renderWithClient(<PredictionLogView />)
    expect(await screen.findByText('口径说明')).toBeTruthy()
    expect(screen.getByText(/命中率仅统计 hit 字段为布尔值的已兑现样本/)).toBeTruthy()
    expect(screen.getByText(/不按「未命中」处理、不补零/)).toBeTruthy()
    expect(screen.getByText(/本页是决策闭环的历史自评记录，不构成未来预测/)).toBeTruthy()
  })
})
