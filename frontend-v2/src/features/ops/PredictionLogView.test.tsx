import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PredictionLogView } from './PredictionLogView'
import type { PredictionLogRow } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({ getPredictionLog: vi.fn() }))
vi.mock('@/api/exportBundle', () => ({
  getRoundtableReportMeta: vi.fn(),
  getRoundtableReportContent: vi.fn(),
  downloadRoundtableReport: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
import { getPredictionLog } from '@/api/read'
import {
  getRoundtableReportMeta,
  getRoundtableReportContent,
  downloadRoundtableReport,
} from '@/api/exportBundle'
const mocked = vi.mocked(getPredictionLog)
const mockedMeta = vi.mocked(getRoundtableReportMeta)
const mockedContent = vi.mocked(getRoundtableReportContent)
const mockedDownload = vi.mocked(downloadRoundtableReport)

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
  mockedMeta.mockReset().mockResolvedValue({
    available: true,
    as_of: '2026-09-11',
    kpis: [{ label: '市场涨占比', value: '11%', meta: '报告快照值' }],
    md_available: true,
    html_available: true,
    source_note: '静态交付物原文，非实时数据',
    reason: null,
  })
  mockedContent.mockReset().mockResolvedValue({
    available: true, format: 'md', filename: 'report.md', mime: 'text/markdown',
    as_of: '2026-09-11', content: '# 报告正文\n\n数据日期：**2026-09-11**', reason: null,
  })
  mockedDownload.mockReset().mockResolvedValue(true)
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

describe('PredictionLogView · 64 静态报告双预览 + 双下载', () => {
  it('真实 KPI 来自报告正文，MD 预览与双格式下载按钮齐备', async () => {
    renderWithClient(<PredictionLogView />)
    expect(await screen.findByText('投研圆桌 · 静态报告（2026-09-11）')).toBeTruthy()
    expect(await screen.findByText('11%')).toBeTruthy()
    expect(await screen.findByText('报告正文')).toBeTruthy()
    expect(screen.getByRole('button', { name: /报告 MD/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /仪表盘 HTML/ })).toBeTruthy()
  })

  it('切到仪表盘预览走 iframe 沙箱，不注入不可信脚本', async () => {
    renderWithClient(<PredictionLogView />)
    fireEvent.click(await screen.findByRole('tab', { name: /仪表盘预览/ }))
    expect(await screen.findByTitle('投研圆桌仪表盘预览')).toBeTruthy()
  })

  it('报告交付物缺失 → 诚实空态，不拿校准日志冒充', async () => {
    mockedMeta.mockResolvedValue({
      available: false, as_of: '2026-09-11', kpis: [], md_available: false,
      html_available: false, source_note: '静态交付物', reason: 'MD / HTML 交付物均缺失',
    })
    renderWithClient(<PredictionLogView />)
    expect(await screen.findByText('静态报告交付物缺失')).toBeTruthy()
    expect(screen.getByText('MD / HTML 交付物均缺失')).toBeTruthy()
  })

  it('下载失败给真实错误提示，不谎报成功', async () => {
    mockedDownload.mockResolvedValue(false)
    renderWithClient(<PredictionLogView />)
    await screen.findByText('11%')  // meta 已 resolve，下载按钮此时才可点
    fireEvent.click(await screen.findByRole('button', { name: /报告 MD/ }))
    expect(await screen.findByText(/未生成空文件/)).toBeTruthy()
  })
})
