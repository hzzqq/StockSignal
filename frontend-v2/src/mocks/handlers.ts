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

export const handlers = [
  // 鉴权（Mock：任意账号通过，签发演示 token）
  http.post('/api/auth/login', () =>
    ok({ access_token: 'mock-access-token', refresh_token: 'mock-refresh-token', token_type: 'Bearer', expires_in: 3600 }),
  ),
  http.post('/api/auth/refresh', () =>
    ok({ access_token: 'mock-access-token', token_type: 'Bearer' }),
  ),
  http.get('/api/health', () =>
    ok({ service: 'stock-signal', status: 'alive', components: { backend: 'ok', database: 'ok' } }),
  ),

  // W1 只读端点
  http.get('/api/v2/read/daily-snapshot', () => ok(fixtures.dailySnapshot)),
  http.get('/api/v2/read/snapshot-dates', () => ok(fixtures.snapshotDates)),
  http.get('/api/v2/read/snapshot/:date', ({ params }) => {
    const d = String(params.date)
    const snap = fixtures.snapshots[d] ?? fixtures.dailySnapshot
    return ok(snap)
  }),
  http.get('/api/v2/read/p1-signals', () => ok(fixtures.p1Signals)),
  http.get('/api/v2/read/daily-recommendation', () => ok(fixtures.recommendation)),
  http.get('/api/v2/read/virtual-users-sim', () => ok(fixtures.virtualSim)),
  http.get('/api/v2/read/paper-trades', ({ request }) => {
    const url = new URL(request.url)
    const user = url.searchParams.get('user') || 'admin'
    return ok(fixtures.paperTrades[user] ?? fixtures.paperTrades.admin)
  }),
  // 以下数据源在本仓当前缺失 → 返回 not_found（前端诚实渲染「无数据」）
  http.get('/api/v2/read/review-notes', () => notFound('review_notes_*.md')),
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
  // W4-A · 个股六维评分：按 code query 分派；非法/缺 code 返回 400 invalid_param 信封。
  http.get('/api/v2/read/six-dim', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 6 位数字', data: null },
        { status: 400 },
      )
    }
    return ok(code === '000001' ? fixtures.sixDimPartial : fixtures.sixDimFull)
  }),

  // W4-B · 个股域三端点：一律按 code query 分派 4 形态；非法/缺 code 返回 400 invalid_param 信封。
  http.get('/api/v2/read/fundamentals', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 6 位数字', data: null },
        { status: 400 },
      )
    }
    if (code === '000002') return ok(fixtures.fundamentalsNullFields)
    if (code === '000003') return ok(fixtures.fundamentalsPerfNull)
    if (code === '000004') return ok(fixtures.fundamentalsDateNull)
    return ok(fixtures.fundamentalsFull)
  }),
  http.get('/api/v2/read/financials', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 6 位数字', data: null },
        { status: 400 },
      )
    }
    if (code === '000002') return ok(fixtures.financialsNullFields)
    if (code === '000003') return ok(fixtures.financialsEmptyRows)
    if (code === '000004') return ok(fixtures.financialsDateNull)
    return ok(fixtures.financialsFull)
  }),
  http.get('/api/v2/read/stock-kline', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 6 位数字', data: null },
        { status: 400 },
      )
    }
    if (code === '000002') return ok(fixtures.klineNullFields)
    if (code === '000003') return ok(fixtures.klineEmptyRows)
    if (code === '000004') return ok(fixtures.klineDateNull)
    return ok(fixtures.klineFull)
  }),

  // W4-C · 多股对比：单股通用快照（按 code 分派 4 态；非法/缺 code → 400）。
  http.get('/api/v2/read/compare-one', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 6 位数字', data: null },
        { status: 400 },
      )
    }
    if (code === '000002') return ok(fixtures.compareOneNullFields)
    if (code === '000003') return ok(fixtures.compareOneEmpty)
    if (code === '000004') return ok(fixtures.compareOneDateNull)
    return ok(fixtures.compareOneFull)
  }),

  // W4-C · 深度分析：600519 已接入（含技术字段），其余合法码返回豁免态。
  http.get('/api/v2/read/research-deep', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 6 位数字', data: null },
        { status: 400 },
      )
    }
    if (code === '600519') return ok(fixtures.researchDeepFull)
    return ok(fixtures.researchDeepExempt)
  }),

  // W4-C · 分时：600519 有昨收基准（前端画基准虚线）；000002 昨收取不到（prev_close=null，
  // 前端不画基准并如实标注）；其余合法码按后端契约 not_found。
  http.get('/api/v2/read/stock-intraday', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 6 位数字', data: null },
        { status: 400 },
      )
    }
    if (code === '600519') return ok(fixtures.stockIntradayFull)
    if (code === '000002') return ok(fixtures.stockIntradayNoPrevClose)
    return notFound(`stock_intraday_${code}`)
  }),

  // 指数行情：index-quotes（外部卡片视角）；index-kline（点击卡片弹 K 线的数据源）。
  http.get('/api/v2/read/index-quotes', () => ok(fixtures.indexQuotes)),
  http.get('/api/v2/read/index-kline', ({ request }) => {
    const code = new URL(request.url).searchParams.get('code')
    if (!code || !/^(sh|sz)\d{6}$/.test(code)) {
      return HttpResponse.json(
        { status: 'error', code: 'invalid_param', message: 'code 须为 sh/sz + 6 位数字', data: null },
        { status: 400 },
      )
    }
    if (code === 'sh000001') return ok(fixtures.indexKlineSh000001)
    return notFound(`index_kline_${code}`)
  }),
]
