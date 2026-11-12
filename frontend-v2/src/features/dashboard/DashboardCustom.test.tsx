import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardCustom } from './DashboardCustom'
import type {
  DailySnapshot,
  DailyRecommendation,
  BreadthPoint,
  EventPool,
  BacktestRuns,
} from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getDailySnapshot: vi.fn(),
  getDailyRecommendation: vi.fn(),
  getBreadthTimeseries: vi.fn(),
  getEventPool: vi.fn(),
  getBacktestRuns: vi.fn(),
}))
import {
  getDailySnapshot,
  getDailyRecommendation,
  getBreadthTimeseries,
  getEventPool,
  getBacktestRuns,
} from '@/api/read'
const mSnap = vi.mocked(getDailySnapshot)
const mRec = vi.mocked(getDailyRecommendation)
const mBreadth = vi.mocked(getBreadthTimeseries)
const mEvent = vi.mocked(getEventPool)
const mBack = vi.mocked(getBacktestRuns)

const LS_KEY = 'ss-dashboard-widgets-v1'

const snap: DailySnapshot = {
  date: '2026-03-01',
  temperature: 55,
  cycle: '震荡',
  score: 62,
  bias: '中性',
  position: { pct: 70, band: '中高', color: '#000000', reasons: [] },
  indicators: {},
}
const rec: DailyRecommendation = {
  status: 'ok',
  generated_at: '2026-03-01 15:00',
  reason: '市场中性',
  disclaimer: '仅供研究，非投资建议',
}
const breadth: BreadthPoint[] = [
  {
    date: '2026-03-01',
    temperature: 50,
    up_count: 3000,
    down_count: 2000,
    limit_up: 50,
    limit_down: 10,
    red_ratio: 60,
    median_chg: 1.2,
  },
]
const eventPool: EventPool = {
  date: '2026-03-01',
  model: 'P1-v40',
  count: 2,
  pool: [
    { rank: 1, symbol: '600000', score: 0.9, signal: 'long' },
    { rank: 2, symbol: '000001', score: 0.8, signal: 'long' },
  ],
}
const backtest: BacktestRuns = {
  runs: [
    {
      run_id: 'r1',
      summary: {
        ticker: '600000',
        strategy: 'momentum',
        total_return_pct: 12.34,
        max_drawdown_pct: -5.6,
        sharpe_ratio: 1.2,
        win_rate_pct: 55,
        trade_count: 100,
      },
    },
  ],
}

const WIDGET_TITLES = ['今日决策快照', '每日荐股', '广度温度时序', '事件因子池', '回测运行记录']

function setAllHappy() {
  mSnap.mockResolvedValue(snap)
  mRec.mockResolvedValue(rec)
  mBreadth.mockResolvedValue(breadth)
  mEvent.mockResolvedValue(eventPool)
  mBack.mockResolvedValue(backtest)
}

/** jsdom 把内联 style 的 hex 归一化成 rgb，统一抽三元组做断言（rgb(255,77,79)）。 */
function colorTriplet(el: Element | null): string {
  const s = el?.getAttribute('style') ?? ''
  const m = s.match(/rgb\(([^)]+)\)/)
  return m ? m[1].replace(/\s+/g, '') : ''
}

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  localStorage.clear()
  setAllHappy()
})
afterEach(() => {
  localStorage.clear()
})

describe('DashboardCustom · 自定义看板 · 组件清单固定 + 本地持久化 + 诚实渲染', () => {
  it('localStorage 空 → 默认全 5 个 widget 全部渲染', async () => {
    renderWithClient(<DashboardCustom />)
    for (const t of WIDGET_TITLES) {
      expect(await screen.findByText(t)).toBeTruthy()
    }
  })

  it('localStorage 损坏（非 JSON）→ 回落默认全开，不静默吞错', async () => {
    localStorage.setItem(LS_KEY, 'not-json{{')
    renderWithClient(<DashboardCustom />)
    for (const t of WIDGET_TITLES) {
      expect(await screen.findByText(t)).toBeTruthy()
    }
  })

  it('localStorage 为非数组对象 → 回落默认全开', async () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ snapshot: true }))
    renderWithClient(<DashboardCustom />)
    for (const t of WIDGET_TITLES) {
      expect(await screen.findByText(t)).toBeTruthy()
    }
  })

  it('localStorage 显式空数组 [] → 显示「请在「管理组件」中至少启用一个面板」空态', async () => {
    localStorage.setItem(LS_KEY, '[]')
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('请在「管理组件」中至少启用一个面板')).toBeTruthy()
    // 无任何 widget 卡片标题
    for (const t of WIDGET_TITLES) {
      expect(screen.queryByText(t)).toBeNull()
    }
  })

  it('?widgets= 覆盖优先且为只读视图：仅渲染指定项、不回写 localStorage、管理面板被抑制', async () => {
    // 预置一个与 URL 不同的选择，证明 URL 覆盖既不读它也不写回
    localStorage.setItem(LS_KEY, JSON.stringify(['backtest']))
    renderWithClient(<DashboardCustom search={{ widgets: 'snapshot,recommendation' }} />)
    expect(await screen.findByText('今日决策快照')).toBeTruthy()
    expect(screen.getByText('每日荐股')).toBeTruthy()
    expect(screen.queryByText('广度温度时序')).toBeNull()
    expect(screen.queryByText('事件因子池')).toBeNull()
    expect(screen.queryByText('回测运行记录')).toBeNull()
    // localStorage 未被改写
    expect(localStorage.getItem(LS_KEY)).toBe(JSON.stringify(['backtest']))
    // 点「管理组件」后编辑面板不出现（深链只读）
    fireEvent.click(screen.getByRole('button', { name: '管理组件' }))
    expect(screen.queryByText('勾选要展示的组件（自动保存）')).toBeNull()
  })

  it('?widgets= 全为非法 id → 回落默认全开，不崩溃', async () => {
    renderWithClient(<DashboardCustom search={{ widgets: 'foo,bar' }} />)
    for (const t of WIDGET_TITLES) {
      expect(await screen.findByText(t)).toBeTruthy()
    }
  })

  it('localStorage 持久化：初始写回全 5 项；取消勾选 snapshot 后写回 4 项（不含 snapshot）', async () => {
    renderWithClient(<DashboardCustom />)
    await waitFor(() =>
      expect(localStorage.getItem(LS_KEY)).toBe(
        JSON.stringify(['snapshot', 'recommendation', 'breadth', 'event', 'backtest']),
      ),
    )
    fireEvent.click(screen.getByRole('button', { name: '管理组件' }))
    fireEvent.click(screen.getByLabelText('切换组件 今日决策快照'))
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(LS_KEY) as string)
      expect(stored).toHaveLength(4)
      expect(stored).not.toContain('snapshot')
    })
  })

  it('从空数组起步 → 勾选 breadth 后该 widget 出现且写入 localStorage', async () => {
    localStorage.setItem(LS_KEY, '[]')
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('请在「管理组件」中至少启用一个面板')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '管理组件' }))
    fireEvent.click(screen.getByLabelText('切换组件 广度温度时序'))
    expect(await screen.findByText('广度温度时序')).toBeTruthy()
    expect(JSON.parse(localStorage.getItem(LS_KEY) as string)).toEqual(['breadth'])
  })
})

describe('DashboardCustom · 各 widget 四态 + 诚实渲染', () => {
  it('snapshot 成功 → 温度/周期/评分/仓位/仓位档/情绪 如实渲染', async () => {
    renderWithClient(<DashboardCustom />)
    // 先等数据渲染（仓位档「中高」仅成功态出现），再断言其余字段
    expect(await screen.findByText('中高')).toBeTruthy() // 仓位档
    expect(screen.getByText('震荡')).toBeTruthy() // cycle
    expect(screen.getByText('70%')).toBeTruthy() // 仓位 pct
    expect(screen.getByText('中性')).toBeTruthy() // 情绪 bias
  })

  it('snapshot 加载中 → 该卡「加载中…」（仅 snapshot loading，其余 resolved）', async () => {
    mSnap.mockReturnValue(new Promise<DailySnapshot>(() => {}))
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('加载中…')).toBeTruthy()
    expect(screen.getByText('今日决策快照')).toBeTruthy()
  })

  it('snapshot 错误 → 该卡 role=alert，错误如实标注', async () => {
    mSnap.mockRejectedValue(new Error('快照挂了'))
    renderWithClient(<DashboardCustom />)
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('快照挂了')
  })

  it('recommendation 成功 → 状态 / 原因 / 免责声明 如实渲染（不编造标的列表）', async () => {
    renderWithClient(<DashboardCustom />)
    // 先等数据渲染（原因「市场中性」仅成功态出现），再断言其余字段
    expect(await screen.findByText('市场中性')).toBeTruthy() // 原因
    expect(screen.getByText(/推荐状态：ok/)).toBeTruthy() // 状态内嵌于「推荐状态：ok」
    expect(screen.getByText('仅供研究，非投资建议')).toBeTruthy()
  })

  it('breadth 成功 → 最新期温度/涨跌家数/涨跌停/红盘比/中位数涨跌(+1.20%) 渲染', async () => {
    renderWithClient(<DashboardCustom />)
    // 先等数据渲染（红盘比「60%」仅成功态出现），再断言其余字段
    expect(await screen.findByText('60%')).toBeTruthy() // 红盘比
    expect(screen.getByText('3000 / 2000')).toBeTruthy() // 上涨/下跌
    expect(screen.getByText('50 / 10')).toBeTruthy() // 涨停/跌停
    expect(screen.getByText('+1.20%')).toBeTruthy() // 中位数涨跌（红涨）
  })

  it('breadth 中位数 median_chg=null → 显「—」不补 0', async () => {
    mBreadth.mockResolvedValue([
      {
        date: '2026-03-01',
        temperature: 50,
        up_count: 3000,
        down_count: 2000,
        limit_up: 50,
        limit_down: 10,
        red_ratio: 60,
        median_chg: null,
      },
    ])
    mSnap.mockReturnValue(new Promise<DailySnapshot>(() => {}))
    mEvent.mockResolvedValue({ date: '2026-03-01', pool: [] })
    mBack.mockResolvedValue({ runs: [] })
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('60%')).toBeTruthy() // 红盘比（成功态出现）
    expect(screen.getByText('—')).toBeTruthy() // 中位数缺失 → 占位不补 0
  })

  it('breadth 中位数 median_chg=0 → 显「0.00%」真实零值（非「—」）', async () => {
    mBreadth.mockResolvedValue([
      {
        date: '2026-03-01',
        temperature: 50,
        up_count: 3000,
        down_count: 2000,
        limit_up: 50,
        limit_down: 10,
        red_ratio: 60,
        median_chg: 0,
      },
    ])
    mSnap.mockReturnValue(new Promise<DailySnapshot>(() => {}))
    mEvent.mockResolvedValue({ date: '2026-03-01', pool: [] })
    mBack.mockResolvedValue({ runs: [] })
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('60%')).toBeTruthy() // 红盘比（成功态出现）
    expect(screen.getByText('0.00%')).toBeTruthy() // 中位数真实零值
    expect(screen.queryByText('—')).toBeNull()
  })

  it('breadth 空数组 → 「暂无广度时序数据」+ 诚实提示（未做填充）', async () => {
    mBreadth.mockResolvedValue([])
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('暂无广度时序数据')).toBeTruthy()
    expect(screen.getByText('breadth-timeseries 为空数组，未做填充')).toBeTruthy()
  })

  it('breadth 错误 → role=alert', async () => {
    mBreadth.mockRejectedValue(new Error('广度挂了'))
    renderWithClient(<DashboardCustom />)
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('广度挂了')
  })

  it('event 成功 → 模型/数量 + top 列表（symbol/score/signal）渲染', async () => {
    mBack.mockResolvedValue({ runs: [] }) // 隔离，避免回测 ticker 600000 与事件池标的碰撞
    renderWithClient(<DashboardCustom />)
    // 先等数据渲染（模型「P1-v40」仅成功态出现），再断言其余字段
    expect(await screen.findByText(/P1-v40/)).toBeTruthy() // 模型（内嵌于数据日行）
    expect(screen.getByText('600000')).toBeTruthy() // 标的（独立 span）
    expect(screen.getByText(/0\.90/)).toBeTruthy() // score（内嵌于「0.90 · long」）
    expect(screen.getAllByText(/long/).length).toBeGreaterThanOrEqual(1) // signal
  })

  it('event 空 pool → 「事件因子池为空」', async () => {
    mEvent.mockResolvedValue({ date: '2026-03-01', pool: [] })
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('事件因子池为空')).toBeTruthy()
  })

  it('backtest 成功 → 总收益红涨(+12.34% #ff4d4f) / 最大回撤绿跌(-5.60% #00d486)', async () => {
    mEvent.mockResolvedValue({ date: '2026-03-01', pool: [] }) // 隔离 600000，避免与事件池碰撞
    renderWithClient(<DashboardCustom />)
    // 先等数据渲染（总收益「+12.34%」仅成功态出现）
    const up = await screen.findByText('+12.34%')
    const down = screen.getByText('-5.60%')
    expect(colorTriplet(up)).toBe('255,77,79') // 红涨 #ff4d4f
    expect(colorTriplet(down)).toBe('0,212,134') // 绿跌 #00d486
  })

  it('backtest 负收益如实绿跌、不取绝对值：total_return_pct=-10.5 → 「-10.50%」#00d486', async () => {
    mEvent.mockResolvedValue({ date: '2026-03-01', pool: [] })
    mBack.mockResolvedValue({
      runs: [
        {
          run_id: 'r2',
          summary: {
            ticker: '000001',
            strategy: 's',
            total_return_pct: -10.5,
            max_drawdown_pct: null,
            sharpe_ratio: null,
            win_rate_pct: null,
            trade_count: null,
          },
        },
      ],
    })
    renderWithClient(<DashboardCustom />)
    const neg = await screen.findByText('-10.50%')
    expect(colorTriplet(neg)).toBe('0,212,134') // 绿跌 #00d486，绝非取绝对值红涨
  })

  it('backtest 零收益中性灰：total_return_pct=0 → 「0.00%」#9aa0b5', async () => {
    mEvent.mockResolvedValue({ date: '2026-03-01', pool: [] })
    mBack.mockResolvedValue({
      runs: [
        {
          run_id: 'r4',
          summary: {
            ticker: 'x',
            strategy: 'y',
            total_return_pct: 0,
            max_drawdown_pct: null,
            sharpe_ratio: null,
            win_rate_pct: null,
            trade_count: null,
          },
        },
      ],
    })
    renderWithClient(<DashboardCustom />)
    const zero = await screen.findByText('0.00%')
    expect(colorTriplet(zero)).toBe('154,160,181') // 中性灰 #9aa0b5
  })

  it('backtest 空 runs → 「暂无回测运行记录」', async () => {
    mBack.mockResolvedValue({ runs: [] })
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('暂无回测运行记录')).toBeTruthy()
  })

  it('backtest run 无 summary → 「无可用回测摘要」', async () => {
    mBack.mockResolvedValue({ runs: [{ run_id: 'r3' }] })
    renderWithClient(<DashboardCustom />)
    expect(await screen.findByText('无可用回测摘要')).toBeTruthy()
  })
})
