import { http, HttpResponse } from 'msw'
import * as fixtures from './fixtures'

/** 统一成功信封（严格对齐 backend/utils/response.py::_ok_payload）。
 * ⚠️ code 是**字符串业务码**（真后端默认 "ok"），不是数字 0。
 * 历史上此处写 code: 0，导致 MSW 全绿却掩盖了「接真后端时 EnvelopeResponse.parse 全站抛错」。 */
function ok(data: unknown, message = 'ok') {
  return HttpResponse.json({ status: 'ok', code: 'ok', message, data })
}

/** 数据缺失/空：返回 200 + status=error（对齐 read_routes._not_found）。 */
function notFound(label: string) {
  return HttpResponse.json(
    { status: 'error', code: 'not_found', message: `数据文件缺失或为空：${label}`, data: null },
    { status: 200 },
  )
}

/** 缺参 / 参数非法：HTTP 400 + validation_error（对齐 paper-trades / review-notes / snapshot）。 */
function badRequest(message: string) {
  return HttpResponse.json(
    { status: 'error', code: 'validation_error', message, data: null },
    { status: 400 },
  )
}

/** 个股域 code 非法：HTTP 400 + invalid_param（对齐 W4-B/C 端点）。 */
function invalidParam(message: string) {
  return HttpResponse.json(
    { status: 'error', code: 'invalid_param', message, data: null },
    { status: 400 },
  )
}

/** 真实日历校验：2026-13-99 / 2026-02-30 都必须判非法（对齐后端 _valid_date）。 */
function validDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false
  const d = new Date(`${s}T00:00:00Z`)
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s
}

export const handlers = [
  // 鉴权（Mock：任意账号通过，签发演示 token）
  http.post('/api/auth/login', () =>
    ok({ access_token: 'mock-access-token', refresh_token: 'mock-refresh-token', token_type: 'Bearer', expires_in: 3600 }),
  ),
  http.post('/api/auth/refresh', () =>
    ok({ access_token: 'mock-access-token', token_type: 'Bearer' }),
  ),
  // 健康检测：显式带 source 标记，前端/测试可据实识别「这不是真实后端」。
  http.get('/api/health', () =>
    ok({ service: 'stock-signal', status: 'alive', source: 'msw-mock', components: { backend: 'ok', database: 'ok' } }),
  ),

  // W1 只读端点
  http.get('/api/v2/read/daily-snapshot', () => ok(fixtures.dailySnapshot)),
  http.get('/api/v2/read/snapshot-dates', () => ok(fixtures.snapshotDates)),
  // 未知归档日期必须诚实 not_found，绝不回退今日快照冒充历史回放。
  http.get('/api/v2/read/snapshot/:date', ({ params }) => {
    const d = String(params.date)
    if (!validDate(d)) return badRequest('日期格式非法（须为真实 YYYY-MM-DD）')
    const snap = fixtures.snapshots[d]
    return snap ? ok(snap) : notFound(`snapshots/${d}.json`)
  }),
  http.get('/api/v2/read/p1-signals', () => ok(fixtures.p1Signals)),
  http.get('/api/v2/read/daily-recommendation', () => ok(fixtures.recommendation)),
  http.get('/api/v2/read/virtual-users-sim', () => ok(fixtures.virtualSim)),
  // 真后端缺 user 即 400；未知用户如实 not_found，不回退 admin 账本。
  http.get('/api/v2/read/paper-trades', ({ request }) => {
    const user = new URL(request.url).searchParams.get('user') ?? ''
    if (!/^[A-Za-z0-9_]{1,64}$/.test(user)) {
      return badRequest('user 非法（仅允许字母/数字/下划线，≤64）')
    }
    const book = fixtures.paperTrades[user]
    return book ? ok(book) : notFound(`paper_${user}.json`)
  }),
  // 以下数据源在本仓当前缺失 → 返回 not_found（前端诚实渲染「无数据」）；
  // review-notes 缺 date 时按真后端返回 400 validation_error。
  http.get('/api/v2/read/review-notes', ({ request }) => {
    const date = new URL(request.url).searchParams.get('date') ?? ''
    if (!validDate(date)) return badRequest('date 非法（须为真实 YYYY-MM-DD）')
    return notFound(`review_notes_${date}.md`)
  }),
  http.get('/api/v2/read/alert-rules', () => notFound('alert_rules.json')),
  http.get('/api/v2/read/alert-log', () => notFound('alerts.log')),
  http.get('/api/v2/read/user-dashboard', () => notFound('user_dashboard.json')),
  http.get('/api/v2/read/webapps', () => ok(fixtures.webapps)),
  // W3 新增只读端点
  http.get('/api/v2/read/breadth-timeseries', () => ok(fixtures.breadthTimeseries)),
  http.get('/api/v2/read/ladder-detail', () => ok(fixtures.ladderDetail)),
  http.get('/api/v2/read/breadth-history', () => ok(fixtures.breadthHistory)),
  // W3 后续簇 · 5 个真实数据源（字段名真扫对齐，数值为演示）
  // p1-sync-status 的 fixture 刻意不含 target_dir，与后端递归脱敏行为一致。
  http.get('/api/v2/read/event-pool', () => ok(fixtures.eventPool)),
  http.get('/api/v2/read/prediction-log', () => ok(fixtures.predictionLog)),
  http.get('/api/v2/read/p1-sync-status', () => ok(fixtures.p1SyncStatus)),
  http.get('/api/v2/read/backtest-runs', () => ok(fixtures.backtestRuns)),
  http.get('/api/v2/read/data-refresh-state', () => ok(fixtures.dataRefreshState)),
  // 因子分析（71 页 V2 化）：结构对齐后端 factor_analysis()；演示数值非真实行情。
  http.get('/api/v2/read/factor-analysis', () => ok(fixtures.factorAnalysis)),
  // 策略回测（30 页 V2 化）：结构对齐后端 backtest()；演示数值非真实行情。
  http.get('/api/v2/read/backtest', () => ok(fixtures.backtest)),
  // 市场全景 / 状态机（56/57 页 V2 化）：结构对齐后端 market-panorama()；演示数值非真实行情。
  http.get('/api/v2/read/market-panorama', () => ok(fixtures.marketPanorama)),
  // 持仓中心（45 页 V2 化）：结构对齐后端 portfolio()；演示数值非真实行情。
  http.get('/api/v2/read/portfolio', () => ok(fixtures.portfolio)),
  // 资金流向（35 页 V2 化）：结构对齐后端 fund_flow()；演示数值非真实行情，金额已折算为亿元。
  http.get('/api/v2/read/fund-flow', () => ok(fixtures.fundFlow)),
  // 实盘交易只读概览（43 页 V2 化）：结构对齐后端 trading_account()；演示数值为本地模拟账本，非真实券商。
  http.get('/api/v2/read/trading-account', () => ok(fixtures.tradingAccount)),
  // W4-A · 个股六维评分：按 code query 分派；非法/缺 code 返回 400 invalid_param 信封。
  http.get('/api/v2/read/six-dim', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    return ok(code === '000001' ? fixtures.sixDimPartial : fixtures.sixDimFull)
  }),

  // W4-B · 个股域三端点：一律按 code query 分派 4 形态；非法/缺 code 返回 400 invalid_param 信封。
  http.get('/api/v2/read/fundamentals', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    if (code === '000002') return ok(fixtures.fundamentalsNullFields)
    if (code === '000003') return ok(fixtures.fundamentalsPerfNull)
    if (code === '000004') return ok(fixtures.fundamentalsDateNull)
    return ok(fixtures.fundamentalsFull)
  }),
  http.get('/api/v2/read/financials', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    if (code === '000002') return ok(fixtures.financialsNullFields)
    if (code === '000003') return ok(fixtures.financialsEmptyRows)
    if (code === '000004') return ok(fixtures.financialsDateNull)
    return ok(fixtures.financialsFull)
  }),
  http.get('/api/v2/read/stock-kline', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    if (code === '000002') return ok(fixtures.klineNullFields)
    if (code === '000003') return ok(fixtures.klineEmptyRows)
    if (code === '000004') return ok(fixtures.klineDateNull)
    return ok(fixtures.klineFull)
  }),

  // W4-C · 多股对比：单股通用快照（按 code 分派 4 态；非法/缺 code → 400）。
  http.get('/api/v2/read/compare-one', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    if (code === '000002') return ok(fixtures.compareOneNullFields)
    if (code === '000003') return ok(fixtures.compareOneEmpty)
    if (code === '000004') return ok(fixtures.compareOneDateNull)
    return ok(fixtures.compareOneFull)
  }),

  // W4-C · 深度分析：真后端恒 deep_analysis_available=false（56 键异步分析未接入），
  // MSW 不得伪造「600519 已接入」；技术字段仍按真后端形态如实给出。
  http.get('/api/v2/read/research-deep', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    if (code === '600519') return ok(fixtures.researchDeepFull)
    return ok(fixtures.researchDeepExempt)
  }),

  // W4-C · 分时：600519 有昨收基准（前端画基准虚线）；000002 昨收取不到（prev_close=null，
  // 前端不画基准并如实标注）；其余合法码按后端契约 not_found。
  http.get('/api/v2/read/stock-intraday', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    if (code === '600519') return ok(fixtures.stockIntradayFull)
    if (code === '000002') return ok(fixtures.stockIntradayNoPrevClose)
    return notFound(`stock_intraday_${code}`)
  }),

  // W4-D · 数据源 / 接口检测：?probe=1 才返回真实探网样例；?degraded=1 供降级态测试。
  http.get('/api/v2/read/diagnostics', ({ request }) => {
    const q = new URL(request.url).searchParams
    if (q.get('degraded') === '1') return ok(fixtures.diagnosticsDegraded)
    return ok(q.get('probe') === '1' ? fixtures.diagnosticsProbe : fixtures.diagnostics)
  }),

  // 指数行情：index-quotes（外部卡片视角）；index-kline（点击卡片弹 K 线的数据源）。
  http.get('/api/v2/read/index-quotes', () => ok(fixtures.indexQuotes)),
  http.get('/api/v2/read/index-kline', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^(sh|sz)\d{6}$/.test(code)) return invalidParam('code 须为 sh/sz + 6 位数字')
    if (code === 'sh000001') return ok(fixtures.indexKlineSh000001)
    return notFound(`index_kline_${code}`)
  }),
]
