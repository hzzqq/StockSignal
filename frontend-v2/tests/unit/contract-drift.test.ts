/**
 * 契约漂移守卫（#2）—— 跨语言三方对齐：
 *
 *   A. MSW 夹具（mock）↔ TS Zod 契约：每个夹具对象用对应 schema 严格 parse，
 *      锁定「mock 与契约自洽」。CI 可跑，无需后端。
 *   B. 实时后端 JSON ↔ TS Zod 契约（生产 ↔ 契约）：当 env SS_BACKEND_URL 指向一个
 *      运行中的后端时，登录后逐个拉取只读端点，仅对信封 status==='ok' 的 data 跑
 *      schema.parse。这是后端 ↔ 前端契约之间唯一跨语言校验，填补此前完全缺失的缺口
 *      （后端 test_read_routes_integration 只校验信封形状，不校验字段语义；Zod 在 TS 侧）。
 *      无网/鉴权失败的端点记为 SKIP，绝不误报。CI 由 contract-drift-live job
 *      启动真实 Flask 后端并注入 SS_BACKEND_URL 后跑（不再默认跳过）。
 *
 * 设计：A 恒跑；B 需 SS_BACKEND_URL。任一侧真实字段类型/形状漂移都会在此暴露。
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { z } from 'zod'
import * as R from '@/api/schemas/read'
import * as S from '@/api/schemas/stock'
import * as D from '@/api/schemas/diagnostics'
import { StockSearchResultSchema } from '@/api/schemas/stockSearch'
import { EnvelopeResponse } from '@/api/schema'
import * as F from '@/mocks/fixtures'
// v1/v2 parity A 类写端点夹具（三组由各 feature 分文件维护，此处统一纳入漂移守卫）
import { userCollectionsFixturePairs } from '@/mocks/fixturesUserCollections'
import { alertWriteFixturePairs } from '@/mocks/fixturesAlertWrite'
import { communityFixturePairs } from '@/mocks/fixturesCommunity'

// ───────────────────────── A. fixture ↔ Zod ─────────────────────────
type Pair = { name: string; schema: z.ZodTypeAny; samples: unknown[] }

const fixturePairs: Pair[] = [
  { name: 'daily-snapshot', schema: R.DailySnapshotSchema, samples: [F.dailySnapshot] },
  { name: 'snapshot-dates', schema: z.array(z.string()), samples: [F.snapshotDates] },
  {
    name: 'snapshot/<date>',
    schema: R.DailySnapshotSchema,
    samples: Object.values(F.snapshots),
  },
  {
    name: 'p1-signals',
    schema: z.record(z.string(), R.P1SignalSchema),
    samples: [F.p1Signals],
  },
  { name: 'daily-recommendation', schema: R.DailyRecommendationSchema, samples: [F.recommendation] },
  { name: 'virtual-users-sim', schema: R.VirtualUsersSimSchema, samples: [F.virtualSim] },
  {
    name: 'paper-trades',
    schema: R.PaperTradeSchema,
    samples: Object.values(F.paperTrades) as unknown[],
  },
  { name: 'user-dashboard', schema: R.UserDashboardSchema, samples: [F.userDashboard] },
  { name: 'earnings-calendar', schema: R.EarningsCalendarSchema, samples: [F.earningsCalendar] },
  { name: 'breadth-analytics', schema: R.BreadthAnalyticsSchema, samples: [F.breadthAnalytics] },
  { name: 'breadth-zseries', schema: R.ZSeriesSchema, samples: [F.breadthZSeries] },
  { name: 'webapps', schema: z.array(R.WebAppSchema), samples: [F.webapps] },
  { name: 'breadth-timeseries', schema: z.array(R.BreadthPointSchema), samples: [F.breadthTimeseries] },
  {
    name: 'ladder-detail',
    schema: z.array(R.LadderDaySchema),
    // 真实后端对历史日 suspect=null（诚实「未判定」），MSW 夹具只给布尔会掩盖该空态；
    // 此处补一条含 null 的数组变体，锁定契约允许 null，防止 mock↔production 漂移复发。
    samples: [
      F.ladderDetail,
      Array.isArray(F.ladderDetail) && F.ladderDetail.length
        ? [{ ...F.ladderDetail[0], suspect: null }]
        : [{ date: '2026-01-01', suspect: null }],
    ],
  },
  { name: 'breadth-history', schema: z.array(R.BreadthHistoryPointSchema), samples: [F.breadthHistory] },
  { name: 'event-pool', schema: R.EventPoolSchema, samples: [F.eventPool] },
  { name: 'prediction-log', schema: z.array(R.PredictionLogRowSchema), samples: [F.predictionLog] },
  { name: 'p1-sync-status', schema: R.P1SyncStatusSchema, samples: [F.p1SyncStatus] },
  { name: 'backtest-runs', schema: R.BacktestRunsSchema, samples: [F.backtestRuns] },
  { name: 'data-refresh-state', schema: R.DataRefreshStateSchema, samples: [F.dataRefreshState] },
  { name: 'momentum-breadth', schema: R.MomentumBreadthSchema, samples: [F.momentumBreadth] },
  { name: 'limit-up-review', schema: R.LimitUpReviewSchema, samples: [F.limitUpReview] },
  { name: 'market-sentiment', schema: R.MarketSentimentSchema, samples: [F.marketSentiment] },
  { name: 'factor-analysis', schema: R.FactorAnalysisSchema, samples: [F.factorAnalysis] },
  { name: 'backtest', schema: R.BacktestSchema, samples: [F.backtest] },
  { name: 'market-panorama', schema: R.MarketPanoramaSchema, samples: [F.marketPanorama] },
  { name: 'portfolio', schema: R.PortfolioSchema, samples: [F.portfolio] },
  // 98 仓位落地（V2 化）：ok + 诚实降级空态（无分配、Σ权重为 null，绝不补零）
  {
    name: 'position-allocation',
    schema: R.PositionAllocationSchema,
    samples: [
      F.positionAllocation,
      { ...F.positionAllocation, allocations: [], excluded: [],
        meta: { ...F.positionAllocation.meta, sum_pct: null, n_alloc: null } },
    ],
  },
  // 81 NL 选股语义解析：ok + spec=null（后端诚实降级）+ 未识别词变体
  {
    name: 'nl-screen',
    schema: R.NlScreenSchema,
    samples: [
      F.nlScreen,
      { ...F.nlScreen, spec: null },
      { ...F.nlScreen,
        spec: { ...F.nlScreen.spec, sort: null, limit: null, unparsed: ['无法识别的短语'], errors: [] } },
    ],
  },
  { name: 'fund-flow', schema: R.FundFlowSchema, samples: [F.fundFlow] },
  { name: 'trading-account', schema: R.TradingAccountSchema, samples: [F.tradingAccount] },
  { name: 'macro-data', schema: R.MacroDataSchema, samples: [F.macroData] },
  { name: 'dragon-tiger', schema: R.DragonTigerSchema, samples: [F.dragonTiger] },
  { name: 'theme', schema: R.ThemeSchema, samples: [F.theme] },
  { name: 'theme-transmission', schema: R.ThemeTransmissionSchema, samples: [F.themeTransmission] },
  { name: 'strong', schema: R.StrongSchema, samples: [F.strong] },
  { name: 'sector-rotation', schema: R.SectorRotationSchema, samples: [F.sectorRotation] },
  { name: 'watch', schema: R.WatchSchema, samples: [F.watch] },
  { name: 'quote-board', schema: R.QuoteBoardSchema, samples: [F.quoteBoard] },
  // 事件因子回测：含 z 有值 + z=null 小样本两种变体，锁定 z 可空契约（诚实空态不补零）
  { name: 'event-backtest', schema: R.EventBacktestSchema, samples: [F.eventBacktest, F.eventBacktestSmallSample] },
  // W4-A/B/C/D 个股域：含 null/empty 变体，确保契约接受诚实空态（不补零）
  { name: 'six-dim', schema: S.SixDimSchema, samples: [F.sixDimFull, F.sixDimPartial] },
  {
    name: 'fundamentals',
    schema: S.FundamentalsSchema,
    samples: [F.fundamentalsFull, F.fundamentalsNullFields, F.fundamentalsPerfNull, F.fundamentalsDateNull],
  },
  {
    name: 'financials',
    schema: S.FinancialsSchema,
    samples: [F.financialsFull, F.financialsNullFields, F.financialsEmptyRows, F.financialsDateNull],
  },
  {
    name: 'stock-kline',
    schema: S.StockKlineSchema,
    samples: [F.klineFull, F.klineNullFields, F.klineEmptyRows, F.klineDateNull],
  },
  {
    name: 'compare-one',
    schema: S.CompareOneSchema,
    samples: [F.compareOneFull, F.compareOneNullFields, F.compareOneEmpty, F.compareOneDateNull],
  },
  {
    name: 'research-deep',
    schema: S.ResearchDeepSchema,
    samples: [F.researchDeepFull, F.researchDeepExempt],
  },
  {
    name: 'stock-intraday',
    schema: S.StockIntradaySchema,
    samples: [F.stockIntradayFull, F.stockIntradayNoPrevClose],
  },
  { name: 'index-quotes', schema: S.IndexQuotesSchema, samples: [F.indexQuotes] },
  { name: 'index-kline', schema: S.IndexKlineSchema, samples: [F.indexKlineSh000001] },
  // diagnostics 契约在 api/schemas/diagnostics.ts 有完整独立 schema，
  // api/diagnostics.ts 也已用 DiagnosticsSchema.parse 校验。此处必须真校验，
  // 不能用 z.unknown() 空转：否则夹具/生产的 sources/freshness/endpoints/probe
  // 字段漂移会完全漏检（历史缺陷：守卫自我静音 + 注释与事实不符）。
  { name: 'decision-loop-health', schema: R.DecisionLoopHealthSchema, samples: [F.decisionLoopHealth] },
  { name: 'stock-search', schema: StockSearchResultSchema, samples: [F.stockSearchMoutai, F.stockSearchEmpty] },
  {
    name: 'diagnostics',
    schema: D.DiagnosticsSchema,
    samples: [F.diagnostics, F.diagnosticsDegraded, F.diagnosticsProbe],
  },
  // ─────── v1/v2 parity 批次 A 类写端点（2026-11-16）───────
  // 后端写端点整批悬空是本次审计的核心缺陷；补齐客户端后，其响应夹具必须同样受
  // 「mock ↔ Zod 契约」硬约束，否则 MSW 全绿但接真后端时字段形状漂移会全站漏检。
  ...userCollectionsFixturePairs,
  ...alertWriteFixturePairs,
  ...communityFixturePairs,
]

describe('contract-drift A: MSW fixtures satisfy Zod schemas (mock ↔ contract)', () => {
  for (const p of fixturePairs) {
    it(`fixture[${p.name}] × ${p.samples.length} 变体`, () => {
      for (const sample of p.samples) {
        const res = p.schema.safeParse(sample)
        expect(
          res.success,
          `fixture "${p.name}" 违反契约 Zod：${res.success ? '' : JSON.stringify((res as { error?: { issues?: unknown[] } }).error?.issues)}`,
        ).toBe(true)
      }
    })
  }
})

// ───────────── B. 实时后端 JSON ↔ Zod（生产 ↔ 契约，需 SS_BACKEND_URL）─────────────
const BASE = process.env.SS_BACKEND_URL

/** 诚实降级信封：error 不得偷偷塞 data，必须给非空原因与业务码。
 *  B 段不再「SKIP 了事」——无数据的端点也要被检查，覆盖才谈得上全量。 */
const DegradedEnvelope = z.object({
  status: z.literal('error'),
  code: z.string().min(1),
  message: z.string().min(1),
  data: z.null(),
})

type LiveCase = { key: string; url: string; schema: z.ZodTypeAny }

const liveCases: LiveCase[] = [
  { key: 'daily-snapshot', url: '/api/v2/read/daily-snapshot', schema: R.DailySnapshotSchema },
  { key: 'snapshot-dates', url: '/api/v2/read/snapshot-dates', schema: z.array(z.string()) },
  { key: 'p1-signals', url: '/api/v2/read/p1-signals', schema: z.record(z.string(), R.P1SignalSchema) },
  { key: 'daily-recommendation', url: '/api/v2/read/daily-recommendation', schema: R.DailyRecommendationSchema },
  { key: 'virtual-users-sim', url: '/api/v2/read/virtual-users-sim', schema: R.VirtualUsersSimSchema },
  { key: 'paper-trades', url: '/api/v2/read/paper-trades?user=admin', schema: R.PaperTradeSchema },
  { key: 'user-dashboard', url: '/api/v2/read/user-dashboard', schema: R.UserDashboardSchema },
  { key: 'earnings-calendar', url: '/api/v2/read/earnings-calendar?market=%E6%B2%AA%E6%B7%B1%E4%BA%AC&period=2025%E5%B9%B4%E6%8A%A5', schema: R.EarningsCalendarSchema },
  { key: 'breadth-analytics', url: '/api/v2/read/breadth-analytics?window=250', schema: R.BreadthAnalyticsSchema },
  { key: 'breadth-zseries', url: '/api/v2/read/breadth-zseries?dim=__DIM__&window=250', schema: R.ZSeriesSchema },
  { key: 'momentum-breadth', url: '/api/v2/read/momentum-breadth', schema: R.MomentumBreadthSchema },
  { key: 'limit-up-review', url: '/api/v2/read/limit-up-review', schema: R.LimitUpReviewSchema },
  { key: 'market-sentiment', url: '/api/v2/read/market-sentiment?days=180', schema: R.MarketSentimentSchema },
  { key: 'webapps', url: '/api/v2/read/webapps', schema: z.array(R.WebAppSchema) },
  { key: 'breadth-timeseries', url: '/api/v2/read/breadth-timeseries', schema: z.array(R.BreadthPointSchema) },
  { key: 'ladder-detail', url: '/api/v2/read/ladder-detail', schema: z.array(R.LadderDaySchema) },
  { key: 'breadth-history', url: '/api/v2/read/breadth-history', schema: z.array(R.BreadthHistoryPointSchema) },
  { key: 'event-pool', url: '/api/v2/read/event-pool', schema: R.EventPoolSchema },
  { key: 'prediction-log', url: '/api/v2/read/prediction-log', schema: z.array(R.PredictionLogRowSchema) },
  { key: 'p1-sync-status', url: '/api/v2/read/p1-sync-status', schema: R.P1SyncStatusSchema },
  { key: 'backtest-runs', url: '/api/v2/read/backtest-runs', schema: R.BacktestRunsSchema },
  { key: 'data-refresh-state', url: '/api/v2/read/data-refresh-state', schema: R.DataRefreshStateSchema },
  { key: 'factor-analysis', url: '/api/v2/read/factor-analysis?codes=600519,600660,000001&days=250', schema: R.FactorAnalysisSchema },
  { key: 'backtest', url: '/api/v2/read/backtest?ticker=600519', schema: R.BacktestSchema },
  { key: 'market-panorama', url: '/api/v2/read/market-panorama?k=8', schema: R.MarketPanoramaSchema },
  { key: 'portfolio', url: '/api/v2/read/portfolio', schema: R.PortfolioSchema },
  // 98 仓位落地：生产三源常 unavailable → SKIP（不误报）；ok 时按 Zod 校验分配结构
  { key: 'position-allocation', url: '/api/v2/read/position-allocation?source=recommend', schema: R.PositionAllocationSchema },
  // 81 NL 选股：纯解析端点恒 ok，用真实中文查询校验 QuerySpec 契约
  { key: 'nl-screen', url: '/api/v2/read/nl-screen?query=' + encodeURIComponent('创业板 市盈率<30'), schema: R.NlScreenSchema },
  { key: 'fund-flow', url: '/api/v2/read/fund-flow', schema: R.FundFlowSchema },
  { key: 'trading-account', url: '/api/v2/read/trading-account', schema: R.TradingAccountSchema },
  { key: 'macro-data', url: '/api/v2/read/macro-data', schema: R.MacroDataSchema },
  { key: 'dragon-tiger', url: '/api/v2/read/dragon-tiger', schema: R.DragonTigerSchema },
  { key: 'theme', url: '/api/v2/read/theme', schema: R.ThemeSchema },
  { key: 'theme-transmission', url: '/api/v2/read/theme-transmission?limit=60', schema: R.ThemeTransmissionSchema },
  { key: 'strong', url: '/api/v2/read/strong', schema: R.StrongSchema },
  { key: 'sector-rotation', url: '/api/v2/read/sector-rotation', schema: R.SectorRotationSchema },
  { key: 'watch', url: '/api/v2/read/watch', schema: R.WatchSchema },
  { key: 'quote-board', url: '/api/v2/read/quote-board', schema: R.QuoteBoardSchema },
  { key: 'event-backtest', url: '/api/v2/read/event-backtest?metric=limit_down_ratio&quantile=0.1&direction=high&horizon=1', schema: R.EventBacktestSchema },
  { key: 'six-dim', url: '/api/v2/read/six-dim?code=600519', schema: S.SixDimSchema },
  { key: 'fundamentals', url: '/api/v2/read/fundamentals?code=600519', schema: S.FundamentalsSchema },
  { key: 'financials', url: '/api/v2/read/financials?code=600519&report=income', schema: S.FinancialsSchema },
  { key: 'stock-kline', url: '/api/v2/read/stock-kline?code=600519', schema: S.StockKlineSchema },
  { key: 'compare-one', url: '/api/v2/read/compare-one?code=600519', schema: S.CompareOneSchema },
  { key: 'research-deep', url: '/api/v2/read/research-deep?code=600519', schema: S.ResearchDeepSchema },
  { key: 'stock-intraday', url: '/api/v2/read/stock-intraday?code=600519', schema: S.StockIntradaySchema },
  { key: 'decision-loop-health', url: '/api/v2/read/decision-loop-health', schema: R.DecisionLoopHealthSchema },
  { key: 'stock-search', url: '/api/stocks/search?q=600519', schema: StockSearchResultSchema },
  { key: 'diagnostics', url: '/api/v2/read/diagnostics', schema: D.DiagnosticsSchema },
  { key: 'index-quotes', url: '/api/v2/read/index-quotes', schema: S.IndexQuotesSchema },
  { key: 'index-kline', url: '/api/v2/read/index-kline?code=sh000001', schema: S.IndexKlineSchema },
]

describe.skipIf(!BASE)('contract-drift B: live backend JSON satisfies Zod (production ↔ contract)', () => {
  let token = ''
  let dim = 'adverse_adverse_ratio' // 兜底，beforeAll 会覆盖

  beforeAll(async () => {
    const loginRes = await fetch(`${BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'Admin@123' }),
    })
    const loginJson = await loginRes.json()
    expect(loginJson.status, `登录失败：${JSON.stringify(loginJson)}`).toBe('ok')
    token = (loginJson.data as { token: string }).token

    // 取一个可靠广度字段用于 zseries 动态用例
    const baRes = await fetch(`${BASE}/api/v2/read/breadth-analytics?window=250`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const baEnv = EnvelopeResponse.safeParse(await baRes.json())
    if (baEnv.success && baEnv.data.status === 'ok') {
      const dims = (baEnv.data.data as { reliable_dims?: string[] })?.reliable_dims
      if (Array.isArray(dims) && dims.length) dim = dims[0]
    }
  }, 60000)

  it(
    '每个只读端点 data 通过对应 Zod 契约（status=ok 者）',
    async () => {
      const results: string[] = []
      let mismatches = 0
      let okCount = 0
      let checkedCount = 0

      for (const c of liveCases) {
        let url = c.url
        if (url.includes('__DIM__')) url = url.replace('__DIM__', encodeURIComponent(dim))
        const abs = `${BASE}${url}`
        // 每个请求独立 12s 超时（勿用全局，否则后续请求被连坐 abort）
        const ac = new AbortController()
        const timer = setTimeout(() => ac.abort(), 12000)
        let status = ''
        let detail = ''
        try {
          const r = await fetch(abs, {
            headers: { Authorization: `Bearer ${token}` },
            signal: ac.signal,
          })
          const json = await r.json()
          const env = EnvelopeResponse.safeParse(json)
          if (!env.success) {
            status = 'ENVELOPE_INVALID'
            detail = JSON.stringify(env.error.issues)
          } else if (env.data.status !== 'ok') {
            const degraded = DegradedEnvelope.safeParse(json)
            if (!degraded.success) {
              status = 'DEGRADED_INVALID'
              mismatches++
              detail = JSON.stringify(degraded.error.issues)
            } else {
              status = `SKIP(${env.data.code})` // 诚实降级：已校验信封，不算契约漂移
              checkedCount++
            }
          } else {
            const parsed = c.schema.safeParse(env.data.data)
            if (parsed.success) { status = 'OK'; okCount++; checkedCount++ }
            else {
              status = 'MISMATCH'
              mismatches++
              detail = JSON.stringify(parsed.error.issues)
            }
          }
        } catch (e) {
          status = 'FETCH_ERR'
          detail = e instanceof Error ? e.message : String(e)
        } finally {
          clearTimeout(timer)
        }
        const line = `[${status}] ${c.key}${detail ? ' :: ' + detail : ''}`
        results.push(line)
      }
      const summary = results.join('\n')
      // 打印便于人工目检
      console.log(`\n=== contract-drift B scan (dim=${dim}) ===\n${summary}\n=== end ===`)
      // 防守卫自我静音：CI 无行情数据（data/ 全 gitignored）时多数端点如实 SKIP，
      // 但恒 ok 的端点（nl-screen / diagnostics 等）必须真被 Zod 校验过；
      // 全线 SKIP/FETCH_ERR 却 0 mismatch 是「伪绿」，必须判失败。
      expect(
        okCount,
        `B 段未真正校验到端点（全线 SKIP/FETCH_ERR = 守卫自我静音）。okCount=${okCount}，汇总：\n${summary}`,
      ).toBeGreaterThanOrEqual(2)
      // 覆盖门禁：OK + 合法降级都算「真检查过」；大面积 FETCH_ERR 却 0 mismatch 属伪绿。
      expect(
        checkedCount,
        `B 段覆盖率不足：${checkedCount}/${liveCases.length} 个端点被真检查。汇总：\n${summary}`,
      ).toBeGreaterThanOrEqual(Math.floor(liveCases.length * 0.8))
      expect(
        mismatches,
        `发现 ${mismatches} 处生产 JSON ↔ Zod 契约漂移：\n${summary}`,
      ).toBe(0)
    },
    600000,
  )
})
