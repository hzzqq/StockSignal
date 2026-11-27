import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { MarketTemperature } from '@/api/schemas/read'
import { BreadthOverview } from './BreadthOverview'

/**
 * 59 市场温度计四块迁移回归（2026-11-20）：
 * 牧羊人指标热度贡献 / 极端区信号（sentiment_edge）/ 历史情境类比 / 基准窗口切换。
 * 与 MarketPanorama.test 同手法：mock @/api/read + QueryClientProvider + 桩掉 EChart（jsdom 无 canvas）。
 */
vi.mock('@/api/read', () => ({
  getDailySnapshot: vi.fn(),
  getBreadthTimeseries: vi.fn(),
  getLadderDetail: vi.fn(),
  getBreadthHistory: vi.fn(),
  getMarketTemperature: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))
import {
  getDailySnapshot,
  getBreadthTimeseries,
  getLadderDetail,
  getBreadthHistory,
  getMarketTemperature,
} from '@/api/read'

const mockedTemp = vi.mocked(getMarketTemperature)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const snap = {
  date: '2026-03-01',
  temperature: 63.2,
  cycle: '活跃',
  indicators: { red_ratio: 52.0 },
  score: 66,
  bias: '多',
}

/** 触发极端区信号的样本（含 hits 表 + 边际）+ 一个 d20 全缺失的类比日（守卫「缺失显 — 不补 0」）。 */
const triggeredData: MarketTemperature = {
  hist_days: 2000,
  data_as_of: '2026-03-01',
  temperature: {
    available: true,
    temp: 88.5,
    contributions: [
      { key: 'red_ratio', name: '红盘比', unit: '%', dir: 1, value: 78.4, hot: 65, warm: 45, heat: 92.0 },
      { key: 'connect_hl', name: '连板高度', unit: '板', dir: 1, value: 9, hot: 7, warm: 4, heat: 86.0 },
    ],
    reason: null,
    indicators_available: ['red_ratio', 'connect_hl'],
    indicators_unavailable: [['vix', 'VIX 数据缺失']],
  },
  extreme_signal: {
    available: true,
    evaluated: true,
    triggered: true,
    hits: [
      { key: 'connect_hl', name: '连板高度', value: 9, threshold: 8, prob: 0.55, n: 41, z: 3.2, why: '连板高度 9 ≥ 极端阈值 8' },
    ],
    prob: 0.55,
    base_rate: 0.31,
    edge_pp: 24.0,
    strength_hint: '强',
    statement: '市场处于历史极端狂热区，其后 10 日上涨概率高于基准。',
    abstain: false,
    reason: null,
  },
  analogs: {
    available: true,
    today_metrics: { red_ratio: 78.4, limit_up: 112, limit_down: 2 },
    analogs: [
      {
        date: '2015-05-20',
        distance: 0.21,
        metrics: { red_ratio: 77.9, limit_up: 120, limit_down: 1 },
        state: '狂热',
        forward: {
          d5: { avg_red: 58.2, up_frac: 0.66, median_delta: 2.1 },
          d10: { avg_red: 57.0, up_frac: 0.63, median_delta: 1.4 },
          d20: { avg_red: null, up_frac: null, median_delta: null },
        },
      },
    ],
    reason: null,
  },
}

const untriggeredData: MarketTemperature = {
  ...triggeredData,
  temperature: { ...triggeredData.temperature, temp: 45.0 },
  extreme_signal: {
    available: true,
    evaluated: true,
    triggered: false,
    hits: [],
    prob: null,
    base_rate: 0.18,
    edge_pp: null,
    strength_hint: null,
    statement: '近 2000 日内暂无指标进入其极端区，本模块不表态。',
    abstain: true,
    reason: null,
  },
}

const unavailableData: MarketTemperature = {
  hist_days: 60,
  data_as_of: null,
  temperature: { available: false, temp: null, contributions: [], reason: '牧羊人指标数据缺失', indicators_available: [], indicators_unavailable: [] },
  extreme_signal: { available: false, evaluated: false, triggered: false, hits: [], prob: null, base_rate: null, edge_pp: null, strength_hint: null, statement: '', abstain: true, reason: '样本不足，无法评估' },
  analogs: { available: false, today_metrics: null, analogs: [], reason: '历史广度序列缺失' },
}

beforeEach(() => {
  vi.mocked(getDailySnapshot).mockResolvedValue(snap)
  vi.mocked(getBreadthTimeseries).mockResolvedValue([])
  vi.mocked(getLadderDetail).mockResolvedValue([])
  vi.mocked(getBreadthHistory).mockResolvedValue([])
  mockedTemp.mockReset()
})

describe('BreadthOverview · 市场温度计四块（v1 59 迁移）', () => {
  it('触发信号：红色告警卡 + hits 表（name/阈值/prob/z）+ 样本/边际 + 统计概率免责小字', async () => {
    mockedTemp.mockResolvedValue(triggeredData)
    renderWithClient(<BreadthOverview />)
    const alertEl = await screen.findByRole('alert')
    expect(alertEl.textContent).toContain('市场处于历史极端狂热区')
    // hits 表
    expect(screen.getByText('连板高度')).toBeTruthy()
    expect(screen.getByText('8')).toBeTruthy()
    // prob 是 0-1 分数，显示层统一转百分比口径（与 statement 的 55.0% 语义一致）
    expect(screen.getByText('55.0%')).toBeTruthy()
    expect(screen.getByText('3.20')).toBeTruthy()
    // 样本 n 天 · 边际 +edge_pp
    expect(screen.getByText(/样本 41 天 · 边际 24 pp/)).toBeTruthy()
    // 免责小字
    expect(screen.getByText('统计概率，非确定性预测')).toBeTruthy()
    // 牧羊人贡献卡：温度档位（88.5 → 狂热；类比日 state 也叫「狂热」，用 getAllByText 防重复匹配）
    expect(screen.getByText(/88\.50/)).toBeTruthy()
    expect(screen.getAllByText('狂热').length).toBeGreaterThan(0)
    // 不可得指标诚实带出
    expect(screen.getByText(/vix（VIX 数据缺失）/)).toBeTruthy()
  })

  it('未触发：显示 statement（含「本模块不表态」），无告警卡无 hits 表', async () => {
    mockedTemp.mockResolvedValue(untriggeredData)
    renderWithClient(<BreadthOverview />)
    expect(await screen.findByText(/本模块不表态/)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText(/样本 .* 天 · 边际/)).toBeNull()
    // 类比卡固定免责文案
    expect(screen.getByText('历史相似≠预测')).toBeTruthy()
  })

  it('analogs 缺失不补 0：d20 全 null 显「—」，绝不出现编造的 0%', async () => {
    mockedTemp.mockResolvedValue(triggeredData)
    renderWithClient(<BreadthOverview />)
    await screen.findByText('2015-05-20')
    expect(screen.getByText(/相似距离 0\.21/)).toBeTruthy()
    expect(screen.getByText(/后5日红盘率 58\.20%/)).toBeTruthy()
    // up_frac 0.66 > 0.5 显示 66%
    expect(screen.getByText(/后5日上涨占比 66%/)).toBeTruthy()
    // d20 全缺失 → 「—」，且不得渲染成 0
    expect(screen.getByText(/后20日红盘率 —/)).toBeTruthy()
    expect(screen.queryByText(/后20日红盘率 0/)).toBeNull()
    expect(screen.queryByText(/后20日红盘率 0\.00/)).toBeNull()
  })

  it('三卡 available=false：诚实显示各自 reason，不编造数据', async () => {
    mockedTemp.mockResolvedValue(unavailableData)
    renderWithClient(<BreadthOverview />)
    await screen.findByText('牧羊人指标数据缺失')
    expect(screen.getByText('样本不足，无法评估')).toBeTruthy()
    expect(screen.getByText('历史广度序列缺失')).toBeTruthy()
    // 不可得时不出告警与类比卡内容
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText('历史相似≠预测')).toBeNull()
  })

  it('窗口切换：默认全历史 2000，切到近一年后以 250 重取（query 参数随窗口变化）', async () => {
    mockedTemp.mockResolvedValue(untriggeredData)
    renderWithClient(<BreadthOverview />)
    await screen.findByText(/本模块不表态/)
    expect(mockedTemp).toHaveBeenNthCalledWith(1, 2000)
    const select = screen.getByLabelText('温度基准窗口') as HTMLSelectElement
    expect(select.value).toBe('2000')
    fireEvent.change(select, { target: { value: '250' } })
    expect(mockedTemp).toHaveBeenNthCalledWith(2, 250)
    expect(select.value).toBe('250')
  })

  it('age=0 + status=stale → 卡头徽标「数据陈旧」，禁显「数据新鲜」（age 不得掩盖 stale）', async () => {
    vi.mocked(getDailySnapshot).mockResolvedValue({
      ...snap,
      data_age_days: 0,
      data_freshness: { status: 'stale' },
    })
    mockedTemp.mockResolvedValue(untriggeredData)
    renderWithClient(<BreadthOverview />)
    expect(await screen.findByLabelText('数据新鲜度：数据陈旧')).toBeTruthy()
    expect(screen.queryByLabelText('数据新鲜度：数据新鲜')).toBeNull()
  })
})
