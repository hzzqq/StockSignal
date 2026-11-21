// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { stockProfileFull } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { ResearchView, DeepBody } from '@/features/stock/ResearchView'
import {
  submitAnalysisTask,
  getCompositeTaskState,
  setPollTiming,
} from '@/features/stock/scoreTask'
import type { ResearchDeep } from '@/api/schemas/stock'

/**
 * 个股研究页 v2 集成守卫（research-integration）：
 *  ① stock-profile 信息卡：名称/行业 chip + 价格/市值 Stat + date:null 诚实；
 *  ② profile 全源降级：core_business null → 「暂无简介（同花顺源不可用）」；
 *  ③ 技术面 ScoreBar：缺维 null → 「—」不画条（meter 反证）、patterns 空数组诚实；
 *  ④ K 线 OHLC 表折叠：折叠态无 OHLC 行、summary 可见、展开后可见
 *     （mutation 反证：若 CollapsibleCard 恒渲染 children，折叠态断言即红）；
 *  ⑤ DeepBody 深度技术字段折叠卡（默认展开，不破坏 DeepExemptRendering 守卫语义）；
 *  ⑥ 六维嵌入：雷达 EChart + 6 条 ScoreBar + 完整页链接；
 *  ⑦ 五维综合异步任务：提交失败诚实 alert；模块级轮询成功 → done 态结果可查；
 *     同会话切页回来（重新挂载组件）结果仍在（模块级 store 生命周期红线）。
 */

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <a className={className}>{children}</a>
    ),
  }
})

// jsdom 无 canvas：桩掉 EChart（K 线/分时/雷达共用），用 testid 计数。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => <div data-testid="echart" />,
}))

const server = setupServer(...handlers)

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'bypass' })
  // 轮询加速：10ms 间隔 / 3s 上限（仅测试；生产仍 1.5s / 60s）
  setPollTiming(10, 3000)
})
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }

const ok = (data: unknown) =>
  HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data })

function renderView(code: string) {
  return render(
    <Providers>
      <ResearchView search={{ view: 'quick', code }} />
    </Providers>,
  )
}

describe('①② stock-profile 信息卡（名称/简介诚实降级）', () => {
  it('显示名称大字 + 行业/板块 chip + 价格/市值 Stat；date:null → 暂无权威数据日', async () => {
    server.use(
      http.get('/api/v2/read/stock-profile', () =>
        ok({ ...stockProfileFull, industry: '白酒' }),
      ),
    )
    renderView('600519')

    expect(await screen.findByText('贵州茅台', {}, FIND)).toBeTruthy()
    expect(screen.getByText('白酒')).toBeTruthy()
    expect(screen.getByText('沪市主板')).toBeTruthy()
    expect(screen.getByText('600519')).toBeTruthy()
    // 价格 / 市值（fmtNum 两位小数）
    expect(screen.getByText('1523.50')).toBeTruthy()
    expect(screen.getByText('19138.20')).toBeTruthy()
    // 生产 date 恒 null → 诚实提示，不用当前日期冒充
    expect(screen.getByText('暂无权威数据日')).toBeTruthy()
    expect(screen.getByText(/主营茅台酒及系列酒/)).toBeTruthy()
  })

  it('core_business null → 「暂无简介（同花顺源不可用）」，name null → 「—」，不编造', async () => {
    renderView('000002')

    expect(await screen.findByText('暂无简介（同花顺源不可用）', {}, FIND)).toBeTruthy()
    // name / price / market_cap 均降级为「—」（多处）
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3)
  })
})

describe('③ 技术面评分（ScoreBar 缺维诚实）', () => {
  it('动量维 null → 「—」且不画 meter；periods null → 多周期综合「—」；patterns 空 → 无形态信号', async () => {
    server.use(
      http.get('/api/v2/read/technical-score', () =>
        ok({
          code: '600519',
          technical: {
            trend: 72.5,
            momentum: null,
            volume: 58,
            patterns: [],
            overall: 66.8,
          },
          periods: null,
          date: null,
          note: '测试口径：momentum 取数失败，periods 无有效K线',
        }),
      ),
    )
    renderView('600519')

    // 有值维画条
    expect(await screen.findByRole('meter', { name: '趋势' }, FIND)).toBeTruthy()
    // 缺失维：显示「—」，meter 不渲染（mutation 反证：若补 0/补 50 则此处红）
    expect(screen.queryByRole('meter', { name: '动量' })).toBeNull()
    expect(screen.queryByRole('meter', { name: '多周期综合' })).toBeNull()
    expect(screen.getByText('无形态信号')).toBeTruthy()
    // profile 与技术面两处 date:null → 均诚实提示
    expect(screen.getAllByText('暂无权威数据日').length).toBeGreaterThanOrEqual(1)
  })
})

describe('④⑤ 表格折叠', () => {
  it('K 线 OHLC 表折叠态：summary 可见、OHLC 行不渲染；展开后可见（mutation 反证）', async () => {
    renderView('600519')

    const region = await screen.findByRole(
      'region',
      { name: 'K 线 OHLC 数据表（daily）' },
      FIND,
    )
    // 折叠态摘要（fixture klineFull：首行 close 1523.5 / date 2026-11-06 / 3 根）
    expect(region.textContent).toContain('最新收盘 1523.50')
    expect(region.textContent).toContain('权威数据日 2026-11-06')
    expect(region.textContent).toContain('3 根')
    // 折叠态：children 不渲染 → OHLC 列名不可见
    expect(screen.queryByText('open')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()

    // 展开后表格可见
    fireEvent.click(within(region).getByRole('button', { name: '展开 ▾' }))
    expect(await screen.findByRole('table', {}, FIND)).toBeTruthy()
    expect(screen.getByText('open')).toBeTruthy()
  })

  it('DeepBody 深度技术字段折叠卡：默认展开（守卫语义：不点击即见真实字段）+ summary 摘要', () => {
    const data: ResearchDeep = {
      code: '600519',
      name: '贵州茅台',
      date: '2026-11-06',
      deep_analysis_available: false,
      price: 1523,
      pe_ttm: 28.1,
      ma5: 1508,
      ma20: 1476,
      amplitude: 2.21,
      pb: null,
      turnover: null,
      note: '轻量同步技术面已返回',
    }
    render(<DeepBody data={data} />)

    const region = screen.getByRole('region', { name: '深度技术字段' })
    // 默认展开：无需点击即可见表格（与 DeepExemptRendering 守卫同语义）
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByText('1523')).toBeTruthy()
    expect(screen.getByText('28.10')).toBeTruthy()
    // 收起后 summary 摘要可见（price/pe_ttm/ma5，null 用「—」——本例无 null 值字段）
    fireEvent.click(within(region).getByRole('button', { name: '收起 ▴' }))
    expect(screen.queryByRole('table')).toBeNull()
    expect(region.textContent).toContain('price 1523 · pe_ttm 28.10 · ma5 1508')
  })
})

describe('⑥ 六维评分嵌入', () => {
  it('雷达 EChart + 6 条 ScoreBar + coverage<6 提示 + 完整页链接', async () => {
    renderView('000001') // MSW：000001 → sixDimPartial（capital/growth 缺失、coverage=4）

    expect(await screen.findByText('仅 4/6 维有效，缺失维未取到数据', {}, FIND)).toBeTruthy()
    expect(screen.getAllByTestId('echart').length).toBeGreaterThanOrEqual(1)
    for (const label of ['技术', '资金', '价值', '成长', '基本面', '周期']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    // 缺失维 ScoreBar 显示「—」：六维中资金/成长缺失
    const region = screen.getByText('六维评分完整页 →')
    expect(region).toBeTruthy()
  })
})

describe('⑦ 五维综合评分（异步任务）', () => {
  it('提交失败 → 诚实 alert + 可重试，不伪造分数', async () => {
    server.use(
      http.post('/api/tasks/', () =>
        HttpResponse.json(
          { status: 'error', code: 'boom', message: '任务提交失败（演示错误）', data: null },
          { status: 200 },
        ),
      ),
    )
    renderView('600519')

    fireEvent.click(screen.getByRole('button', { name: '生成五维综合评分（异步约 10-30 秒）' }))
    const alert = await screen.findByRole('alert', {}, FIND)
    expect(alert.textContent).toContain('五维综合评分失败')
    expect(alert.textContent).toContain('任务提交失败（演示错误）')
  })

  it('模块级轮询成功 → phase=done，评分键逐字透传', async () => {
    submitAnalysisTask('600520')
    await waitFor(
      () => expect(getCompositeTaskState('600520').phase).toBe('done'),
      { timeout: 5000 },
    )
    const st = getCompositeTaskState('600520')
    expect(st.result?.composite).toBe(74.2)
    expect(st.result?.verdict).toBe('看多')
    expect(st.result?.tech_score).toBe(66.8)
    expect(st.result?.sector_score).toBe(68.9)
  })

  it('同会话切页回来（组件重新挂载）结果仍在：评分环 + verdict 徽标 + 5 条子分', async () => {
    renderView('600520')

    expect(await screen.findByText('看多', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('img', { name: '五维综合评分：74.2' })).toBeTruthy()
    expect(screen.getByText('技术分')).toBeTruthy()
    expect(screen.getByText('66.8')).toBeTruthy()
    expect(screen.getByText('新闻情绪分')).toBeTruthy()
    expect(screen.getByText('板块分')).toBeTruthy()
  })
})
