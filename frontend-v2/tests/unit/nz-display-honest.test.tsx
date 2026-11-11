// @vitest-environment jsdom
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Providers } from '@/app/providers'
import { handlers } from '@/mocks/handlers'
import { Strong } from '@/features/strong/Strong'
import { Watch } from '@/features/watch/Watch'
import { Theme } from '@/features/theme/Theme'

// jsdom 跑不了真实 ECharts canvas；桩掉，专注文本诚实逻辑。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ ariaLabel }: { ariaLabel?: string }) => <div data-testid="echart">{ariaLabel}</div>,
}))

// 安全替身：纯组件内含 <Link> 时不影响渲染。
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, Link: ({ children }: { children?: unknown }) => <a>{children as never}</a>, useNavigate: () => vi.fn() }
})

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => { server.resetHandlers(); cleanup(); localStorage.clear(); vi.restoreAllMocks() })
afterAll(() => server.close())

/**
 * 诚实红线回归（批次 6）：nz() 把 null 补成 0，曾把缺失评分/统计伪装成真实「0 / 0.0 / 0 条」。
 * 这些用例用真 MSW 夹具（缺失字段显式 null）断言用户可见文本显示「—」而非补零。
 */
describe('Strong：缺失评分绝不补零成 0.0', () => {
  it('score=null 的标的与榜首评分显「—」，不出现 0.0', async () => {
    server.use(http.get('/api/v2/read/strong', () => HttpResponse.json({
      status: 'ok', code: 'ok', message: 'ok',
      data: {
        items: [{ rank: 1, code: '688256', name: '寒武纪', price: 95.0, chg: 5.6, amount: 2e9, turnover: 8.0, vol_ratio: 2.1, score: null, s_chg: 96.0, s_vr: 92.0, s_to: 90.0, s_amt: 70.0 }],
        src_label: '东财实时快照（直连）', kicked: [], unavailable: [], date: null,
      },
    })))
    render(<Providers><Strong /></Providers>)
    await screen.findByText('寒武纪') // 数据已加载（heading 在 loading 期即渲染，须等数据依赖节点）
    // 缺失评分 → 显「—」（行内评分 + 榜首评分 Stat 两处，至少 1 个）
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
    // 绝不把 null 补成 0.0
    expect(screen.queryByText('0.0')).toBeNull()
  })
})

describe('Watch：缺失统计绝不补零成 0', () => {
  it('summary 计数为 null → 四项 Stat 显「—」', async () => {
    server.use(http.get('/api/v2/read/watch', () => HttpResponse.json({
      status: 'ok', code: 'ok', message: 'ok',
      data: {
        watchlist: [{ code: '600519', name: '贵州茅台', note: '', fund: { source: 'akshare', main_net: 5.0, main_net_pct: 4.2, big_net: 3.0, super_net: 2.0, latest_date: '2026-11-10' } }],
        sector_items: [],
        summary: { watch_count: null, with_fund: null, strong_count: null, weak_count: null },
        unavailable: [], note: 'x',
      },
    })))
    render(<Providers><Watch /></Providers>)
    await screen.findByText('盯盘数量') // 数据加载后汇总卡才渲染
    for (const label of ['盯盘数量', '有资金流', '强预警', '弱预警']) {
      const lab = screen.getByText(label)
      const card = lab.closest('.rounded-tile')
      const val = card?.querySelector('.text-kpi')
      expect(val?.textContent).toBe('—')
    }
  })
})

describe('Theme：缺失条数绝不补零成 0 条 / 0 个', () => {
  it('传导结果 n_titles/n_concepts 为 null → 显「—」', async () => {
    server.use(http.get('/api/v2/read/theme-transmission', () => HttpResponse.json({
      status: 'ok', code: 'ok', message: 'ok',
      data: { status: 'ok', basis: '文本共现', disclaimer: 'x', entries: [], concepts_hit: [], members_unavailable: [], n_titles: null, n_concepts: null },
    })))
    render(<Providers><Theme /></Providers>)
    await screen.findByText('题材热点')
    fireEvent.click(screen.getByText(/生成传导图谱/))
    await waitFor(
      () => expect(screen.getByText(/新闻标题 — 条｜命中概念 — 个/)).toBeTruthy(),
      { timeout: 5000 },
    )
    expect(screen.queryByText(/新闻标题 0 条/)).toBeNull()
    expect(screen.queryByText(/命中概念 0 个/)).toBeNull()
  })
})
