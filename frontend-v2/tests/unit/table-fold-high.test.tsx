// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { backtest, paperTrades } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { CollapsibleCard } from '@/shared/ui/CollapsibleCard'
import { NlExecutePanel } from '@/features/screener/NlExecutePanel'
import { LimitUpReview } from '@/features/breadth/LimitUpReview'
import { DragonTiger } from '@/features/dragontiger/DragonTiger'
import { EarningsHunterPanel } from '@/features/stock/EarningsHunterPanel'
import { Backtest } from '@/features/backtest/Backtest'
import { PaperTrades } from '@/features/paper/PaperTrades'

/**
 * 表格折叠语义守卫（table-fold-high）· 8 处 CollapsibleCard 改造的行为证据。
 *
 * 每处折叠验证三件事：
 *  ① 折叠态 summary 精确可见（真实可算：命中数 / 家数 / 笔数 / 数据日 / 现金，禁止编造）；
 *  ② 折叠态 table 不渲染（children 折叠时不进 DOM）；
 *  ③ 展开后表格与真实行可见（先展开再断言，不删真实性断言）。
 *
 * QueryState / 空态 / 统计说明必须留在折叠卡外（不被藏匿）——由「折叠态仍可见统计行」隐式验证。
 * 末尾 mutation 反证：临时把 CollapsibleCard 变成「总渲染 children」→ 折叠态表格直接可见，
 * 与用例的反证断言矛盾（变红）→ 还原，证明折叠语义确实由真实组件保证。
 */

// jsdom 无 canvas：与全仓兄弟测试一致，用轻量替身替换真实 EChart；
// 顺带把 option.dataZoom 透出到 data 属性，供资金曲线 dataZoom 断言使用。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ option, height }: { option?: unknown; height?: number }) => (
    <div
      data-testid="echart"
      data-zoom={JSON.stringify(
        Array.isArray((option as { dataZoom?: unknown[] } | undefined)?.dataZoom)
          ? ((option as { dataZoom: Array<{ type: string }> }).dataZoom).map((d) => d.type)
          : null,
      )}
      style={{ height }}
    />
  ),
}))

if (!('ResizeObserver' in globalThis)) {
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }

function renderWith(node: ReactNode) {
  return render(<Providers>{node}</Providers>)
}

/** 在指定折叠卡区域内展开（w4b-pages 同款范式）。 */
async function expandRegion(name: string) {
  const region = await screen.findByRole('region', { name }, FIND)
  fireEvent.click(within(region).getByRole('button', { name: '展开 ▾' }))
  return region
}

// ───────── CollapsibleCard 纯组件语义 ─────────

describe('CollapsibleCard · 折叠语义', () => {
  it('折叠态：summary 可见、children 不渲染、aria-expanded=false；展开后 children 可见、aria-expanded=true', () => {
    render(
      <CollapsibleCard title="测试明细" summary="3 条 · 合计 12.5">
        <table>
          <tbody>
            <tr>
              <td>单元格</td>
            </tr>
          </tbody>
        </table>
      </CollapsibleCard>,
    )
    expect(screen.getByText('3 条 · 合计 12.5')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('单元格')).toBeNull()

    const btn = screen.getByRole('button', { name: '展开 ▾' })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(btn)
    expect(screen.getByRole('button', { name: /收起/ }).getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByText('单元格')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '收起 ▴' }))
    expect(screen.queryByRole('table')).toBeNull()
  })
})

// ───────── 1 · NL 选股执行结果明细 ─────────

describe('NlExecutePanel · 执行结果明细折叠', () => {
  it('折叠态 summary=命中 3 条、表格不渲染；统计行与二道闸信息留在折叠卡外可见；展开后结果行可见', async () => {
    renderWith(<NlExecutePanel />)
    fireEvent.click(screen.getByRole('button', { name: '🚀 执行筛选' }))
    // summary 精确断言（rows.length 真实可算）
    expect(await screen.findByText('命中 3 条', {}, FIND)).toBeTruthy()
    // 候选池/命中/排雷统计行不被折叠藏匿（QueryState 语义必须在折叠卡外）
    expect(screen.getByText(/候选池 5 → 条件命中 3 → 二道闸排雷后 3 行/)).toBeTruthy()
    expect(screen.getByText(/二道闸排除 1 只/)).toBeTruthy()
    // 折叠态反证：结果表不渲染
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('300750')).toBeNull()

    await expandRegion('执行结果明细')
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByText('300750')).toBeTruthy()
    expect(screen.getByText('宁德时代')).toBeTruthy()
  })
})

// ───────── 2 · 涨停复盘：涨停池明细 + 龙头评分榜 ─────────

describe('LimitUpReview · 涨停池明细 / 龙头评分榜折叠', () => {
  it('两表各自折叠：summary=入池 4 家 · 最高 3 板 / 榜单 4 条，折叠态均不渲染表格，展开后可见', async () => {
    renderWith(<LimitUpReview />)
    // 涨停池 summary 精确断言（count / max_boards 真实可算）
    expect(await screen.findByText('入池 4 家 · 最高 3 板', {}, FIND)).toBeTruthy()
    expect(await screen.findByText('榜单 4 条', {}, FIND)).toBeTruthy()
    // 折叠态反证：两张表都不渲染
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('贵州茅台')).toBeNull()

    await expandRegion('涨停池明细')
    const poolTable = screen.getAllByRole('table')
    expect(poolTable.length).toBe(1)
    expect(screen.getByText('首次封板')).toBeTruthy()
    expect(screen.getByText('宁德时代')).toBeTruthy()

    // 收起涨停池明细，再展开龙头评分榜（两卡互不影响）
    fireEvent.click(within(screen.getByRole('region', { name: '涨停池明细' })).getByRole('button', { name: '收起 ▴' }))
    expect(screen.queryByRole('table')).toBeNull()
    await expandRegion('龙头评分榜')
    const board = screen.getByRole('region', { name: '龙头评分榜' })
    expect(within(board).getByText('综合')).toBeTruthy()
    // 中国平安综合分 42.4（榜单真实数值，全榜唯一，避免 100.0 五列同值的多匹配）
    expect(within(board).getByText('42.4')).toBeTruthy()
    expect(screen.getAllByRole('table').length).toBe(1)
  })
})

// ───────── 3 · 龙虎榜：净买/净卖排名表 + 原始明细 ─────────

describe('DragonTiger · 排名表与原始明细折叠', () => {
  it('三张表各自折叠：summary=上榜 3 家 · 数据日 20261109（真实 data_date_available），折叠态不渲染表格，展开后可见', async () => {
    renderWith(<DragonTiger />)
    const summary = '上榜 3 家 · 数据日 20261109'
    expect((await screen.findAllByText(summary, {}, FIND)).length).toBe(3)
    // 折叠态反证：排名表 + 原始明细都不渲染
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('600519')).toBeNull()

    const buyRegion = await expandRegion('🔥 净买入 Top')
    expect(within(buyRegion).getByText('净买额')).toBeTruthy()
    expect(within(buyRegion).getByText('600519')).toBeTruthy()

    const detailRegion = await expandRegion('原始明细（前 3 行）')
    // 原始明细表列名来自后端原始记录
    expect(within(detailRegion).getByText('名称')).toBeTruthy()
    expect(screen.getAllByRole('table').length).toBe(2)
  })
})

// ───────── 4 · 财报猎手 · 业绩预告扫描结果 ─────────

describe('EarningsHunterPanel · 扫描结果折叠', () => {
  it('折叠态 summary=命中数 + 各信号计数（真实统计），表格不渲染；展开后结果行可见', async () => {
    renderWith(<EarningsHunterPanel />)
    fireEvent.click(screen.getByRole('button', { name: '扫描业绩预告' }))
    // 默认条件（20260630 / min_pct=0 / 利好+偏多）对夹具 3 行真实筛选后的统计：
    // 预增→利好、扭亏→利好、略增→偏多 → 命中 3，利好 2、偏多 1、中性/偏空/利空 0
    expect(
      await screen.findByText('命中 3 条 · 利好 2 · 偏多 1 · 中性 0 · 偏空 0 · 利空 0', {}, FIND),
    ).toBeTruthy()
    // 扫描统计与信号级别说明留在折叠卡外（QueryState 语义不被藏匿）
    expect(screen.getByText(/共 5 条预告，筛选命中 3 条/)).toBeTruthy()
    // 折叠态反证：结果表不渲染
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('股票代码')).toBeNull()

    await expandRegion('扫描结果明细')
    expect(screen.getByText('股票代码')).toBeTruthy()
    expect(screen.getByText('600519')).toBeTruthy()
  })
})

// ───────── 5 · 策略回测：逐笔明细折叠 + 资金曲线 dataZoom ─────────

describe('Backtest · 逐笔明细折叠与资金曲线 dataZoom', () => {
  it('折叠态 summary=5 笔 · 累计收益（fixture 真实值）、表格不渲染；展开后表头与行可见', async () => {
    renderWith(<Backtest />)
    expect(await screen.findByText('资金曲线（累计收益 + 回撤）', {}, FIND)).toBeTruthy()
    // summary 精确断言：笔数 + 累计收益（数值来自夹具，不编造）
    expect(
      await screen.findByText(
        `${backtest.trades.length} 笔 · 累计收益 ${Number(backtest.total_return_pct).toFixed(2)}%`,
        {},
        FIND,
      ),
    ).toBeTruthy()
    // 无交易的诚实空态文案不在折叠卡内（trades 非空时也不渲染）——折叠态反证：表不渲染
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('买入日')).toBeNull()

    await expandRegion('逐笔交易明细')
    expect(screen.getByText('买入日')).toBeTruthy()
    expect(screen.getByText('离场原因')).toBeTruthy()
    expect(screen.getByText('止盈')).toBeTruthy()
    expect(screen.getAllByRole('table').length).toBe(1)
  })

  it('资金曲线 EChart option 内置 dataZoom（inside + slider），便于长区间拖拽', async () => {
    renderWith(<Backtest />)
    const echart = await screen.findByTestId('echart', {}, FIND)
    expect(JSON.parse(echart.getAttribute('data-zoom') ?? '[]').sort()).toEqual([
      'inside',
      'slider',
    ])
  })
})

// ───────── 6 · 模拟交易：成交记录折叠、持仓表平铺 ─────────

describe('PaperTrades · 成交记录折叠 / 持仓表不折', () => {
  it('成交记录折叠：summary=笔数 + 当前现金（真实可算），持仓表（1 行 < 10）保持平铺不被折叠', async () => {
    const admin = paperTrades.admin as { cash: number; trades: unknown[] }
    renderWith(<PaperTrades />)
    // 持仓表未折叠：折叠态下它是页面上唯一可见的表
    expect(await screen.findByText('持仓', {}, FIND)).toBeTruthy()
    expect(screen.getByText('贵州茅台')).toBeTruthy()
    expect(screen.getAllByRole('table').length).toBe(1)
    // 成交记录 summary 精确断言：笔数 + 当前现金（toLocaleString 与组件同源）
    expect(
      await screen.findByText(
        `${admin.trades.length} 笔 · 可用现金 ${admin.cash.toLocaleString()}`,
        {},
        FIND,
      ),
    ).toBeTruthy()
    // 折叠态反证：成交记录表不渲染（宁德时代只出现在成交明细里）
    expect(screen.queryByText('宁德时代')).toBeNull()

    await expandRegion('成交记录')
    expect(screen.getByText('宁德时代')).toBeTruthy()
    expect(screen.getAllByRole('table').length).toBe(2)
  })
})

// ───────── mutation 反证 ─────────

describe('mutation 反证 · CollapsibleCard 总渲染 children 则折叠断言变红', () => {
  it('临时变异：折叠态也渲染 children → 成交记录表直接可见（与上一用例的反证断言矛盾）→ 还原', async () => {
    vi.resetModules()
    vi.doMock('@/shared/ui/CollapsibleCard', () => ({
      // 变异体：忽略 open 状态，children 恒渲染（模拟折叠失效的回归形态）
      CollapsibleCard: ({
        title,
        summary,
        children,
      }: {
        title?: ReactNode
        summary?: ReactNode
        children?: ReactNode
      }) => (
        <section role="region" aria-label={typeof title === 'string' ? title : undefined}>
          <p>{summary}</p>
          {children}
        </section>
      ),
    }))
    try {
      const { PaperTrades: MutatedPaperTrades } = await import('@/features/paper/PaperTrades')
      renderWith(<MutatedPaperTrades />)
      await screen.findByText('持仓', {}, FIND)
      // 变异体下：折叠态渲染了两张表（持仓 + 成交记录），且成交明细行直接可见
      // ——这正是不折叠回归发生时、上一用例 `getAllByRole('table').length === 1`
      //   与 `queryByText('宁德时代') === null` 断言会变红的证据。
      expect(screen.getAllByRole('table').length).toBe(2)
      expect(screen.getByText('宁德时代')).toBeTruthy()
    } finally {
      vi.doUnmock('@/shared/ui/CollapsibleCard')
      vi.resetModules()
    }
  })
})
