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
/** 与后端 _ANALYTICS_WINDOWS 一致：非法 window 必须 400，不能静默回落。 */
const ANALYTICS_WINDOWS = [60, 120, 250, 750, 2000]

function analyticsWindow(url: URL): number | null {
  const raw = url.searchParams.get('window')
  if (raw === null || raw === '') return 250
  const v = Number(raw)
  return ANALYTICS_WINDOWS.includes(v) ? v : null
}

function validDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false
  const d = new Date(`${s}T00:00:00Z`)
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s
}

/** 管理端 Mock 的可变状态（模块作用域，供 resetAdminMock 在测试间复位，避免跨测试污染）。
 * 必须在 `handlers` 之前声明：handlers 内的 IIFE 在求值阶段即引用本状态。 */
interface AdminMockState {
  users: any[]
  logs: any[]
  nextId: number
  nextLogId: number
}
const adminMockState: AdminMockState = {
  users: fixtures.adminUsers.map((u) => ({ ...u })),
  logs: fixtures.adminLogs.map((l) => ({ ...l })),
  nextId: Math.max(0, ...fixtures.adminUsers.map((u) => u.id)) + 1,
  nextLogId: Math.max(0, ...fixtures.adminLogs.map((l) => l.id)) + 1,
}

/**
 * 管理端 Mock 生成资源的时间戳（确定性常量，非 new Date()）。
 * 守卫 honest-data.test.tsx 禁止 `new Date()` 冒充数据日；Mock 本就是模拟数据，
 * 统一用与夹具一致的固定 ISO 戳，反而比运行时 now 更利于测试断言与可重现。
 */
const MOCK_CREATED_AT = '2026-01-01T08:00:00Z'

export const handlers = [
  // 鉴权（Mock：任意账号通过，签发演示 token）
  // 登录返回 user（role 由账号决定：admin 账号→管理员，其余→普通用户），与真后端契约一致。
  http.post('/api/auth/login', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { username?: string }
    const role = body.username === 'admin' ? 'admin' : 'user'
    return ok({
      access_token: 'mock-access-token',
      refresh_token: 'mock-refresh-token',
      token_type: 'Bearer',
      expires_in: 3600,
      user: {
        id: role === 'admin' ? 1 : 2,
        username: body.username ?? 'demo',
        role,
        created_at: '2026-01-01T08:00:00Z',
        is_active: true,
        avatar: null,
        settings: {},
      },
    })
  }),
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
  http.get('/api/v2/read/user-dashboard', () => ok(fixtures.userDashboard)),
  http.get('/api/v2/read/earnings-calendar', ({ request }) => {
    const url = new URL(request.url)
    const market = url.searchParams.get('market') || '沪深京'
    const period = url.searchParams.get('period') || '2025年报'
    return ok({ ...fixtures.earningsCalendar, market, period })
  }),
  // 离线可靠广度统计（65/67/68/69）：夹具为真实离线序列末 60 日子集，
  // 故按 window 截尾后把 window 如实回显为**实际点数**，绝不假装拿到更长历史。
  http.get('/api/v2/read/breadth-analytics', ({ request }) => {
    const url = new URL(request.url)
    const w = analyticsWindow(url)
    if (w === null) return badRequest('window 仅允许 60/120/250/750/2000')
    const base = fixtures.breadthAnalytics
    const ser = base.sections.phase.series
    const take = Math.min(w, ser.dates.length)
    const sliced: Record<string, (number | null)[]> = {}
    for (const [k, v] of Object.entries(ser.series)) {
      sliced[k] = (v as (number | null)[]).slice(-take)
    }
    return ok({
      ...base,
      window: take,
      sections: {
        ...base.sections,
        phase: {
          ...base.sections.phase,
          series: { ...ser, dates: ser.dates.slice(-take), series: sliced },
        },
      },
    })
  }),
  // 68 页 z-score 轨迹：dim 必须在可靠字段白名单（对齐后端 REAL_FEATURES 校验）。
  http.get('/api/v2/read/breadth-zseries', ({ request }) => {
    const url = new URL(request.url)
    const w = analyticsWindow(url)
    if (w === null) return badRequest('window 仅允许 60/120/250/750/2000')
    const dim = url.searchParams.get('dim') ?? ''
    const dims = fixtures.breadthAnalytics.reliable_dims
    if (!dims.includes(dim)) return badRequest('dim 非法（须为离线可靠广度字段）')
    const base = fixtures.breadthZSeries
    const take = Math.min(w, base.dates.length)
    const start = base.dates.length - take
    const labels = fixtures.breadthAnalytics.reliable_labels as Record<string, string>
    return ok({
      ...base,
      dim,
      label: labels[dim] ?? dim,
      window: take,
      dates: base.dates.slice(start),
      z: base.z.slice(start),
      raw: base.raw.slice(start),
      markers: base.markers.filter((m) => m >= start).map((m) => m - start),
      note: `${base.note}（MSW 演示夹具仅含末 ${base.dates.length} 日）`,
    })
  }),
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
  // W4-E · 50/62/70 三页数据源（62 离线共振 / 70 实时涨停池 / 50 实时情绪温度计）。
  // 结构与真端点一致；演示数值非真实行情。三端点均优雅回落默认值（不缺参 400），
  // 故不登记 _DIAG_REQUIRED_QUERY；MSW 仅按 needs_params:false 列入诊断端点清单。
  http.get('/api/v2/read/momentum-breadth', () => ok(fixtures.momentumBreadth)),
  http.get('/api/v2/read/limit-up-review', ({ request }) => {
    const date = new URL(request.url).searchParams.get('date')
    return ok(date ? { ...fixtures.limitUpReview, date } : fixtures.limitUpReview)
  }),
  http.get('/api/v2/read/market-sentiment', () => ok(fixtures.marketSentiment)),
  // 因子分析（71 页 V2 化）：结构对齐后端 factor_analysis()；演示数值非真实行情。
  // 回显请求参数（真实后端会回显）；有效标的<3 时诚实返回空序列（insufficient_data）。
  http.get('/api/v2/read/factor-analysis', ({ request }) => {
    const url = new URL(request.url)
    const codesRaw = url.searchParams.get('codes') ?? fixtures.factorAnalysis.codes.join(',')
    const codes = codesRaw.split(',').map((s) => s.trim()).filter((s) => /^\d{6}$/.test(s))
    const factor = url.searchParams.get('factor') ?? fixtures.factorAnalysis.factor
    const days = Number(url.searchParams.get('days') ?? fixtures.factorAnalysis.days)
    const nLayers = Number(url.searchParams.get('n_layers') ?? fixtures.factorAnalysis.n_layers)
    const forward = Number(url.searchParams.get('forward') ?? fixtures.factorAnalysis.forward)
    if (codes.length < 3) {
      return ok({
        ...fixtures.factorAnalysis,
        codes,
        factor,
        days,
        n_layers: nLayers,
        forward,
        ic_series: [],
        layered_cum: [],
        long_short_cum: [],
      })
    }
    return ok({ ...fixtures.factorAnalysis, codes, factor, days, n_layers: nLayers, forward })
  }),
  // 策略回测（30 页 V2 化）：结构对齐后端 backtest()；演示数值非真实行情。
  // 回显请求参数（真实后端会回显 ticker/strategy/start/end），并对哨兵标的 000000 诚实返回空曲线。
  http.get('/api/v2/read/backtest', ({ request }) => {
    const url = new URL(request.url)
    const ticker = url.searchParams.get('ticker') ?? fixtures.backtest.ticker
    const strategy = url.searchParams.get('strategy') ?? fixtures.backtest.strategy
    const start = url.searchParams.get('start') ?? fixtures.backtest.start
    const end = url.searchParams.get('end') ?? fixtures.backtest.end
    if (ticker === '000000') {
      return ok({ ...fixtures.backtest, ticker, strategy, start, end, equity_curve: [], trades: [] })
    }
    return ok({ ...fixtures.backtest, ticker, strategy, start, end })
  }),
  // 市场全景 / 状态机（56/57 页 V2 化）：结构对齐后端 market-panorama()；演示数值非真实行情。
  http.get('/api/v2/read/market-panorama', () => ok(fixtures.marketPanorama)),
  // 持仓中心（45 页 V2 化）：结构对齐后端 portfolio()；演示数值非真实行情。
  http.get('/api/v2/read/portfolio', () => ok(fixtures.portfolio)),
  // 资金流向（35 页 V2 化）：结构对齐后端 fund_flow()；演示数值非真实行情，金额已折算为亿元。
  http.get('/api/v2/read/fund-flow', () => ok(fixtures.fundFlow)),
  // 实盘交易只读概览（43 页 V2 化）：结构对齐后端 trading_account()；演示数值为本地模拟账本，非真实券商。
  http.get('/api/v2/read/trading-account', () => ok(fixtures.tradingAccount)),
  // 宏观数据（84 页 V2 化）：结构对齐后端 macro_data()；演示数值非真实行情，取不到项如实 null。
  http.get('/api/v2/read/macro-data', () => ok(fixtures.macroData)),
  http.get('/api/v2/read/dragon-tiger', () => ok(fixtures.dragonTiger)),
  http.get('/api/v2/read/theme', () => ok(fixtures.theme)),
  http.get('/api/v2/read/theme-transmission', () => ok(fixtures.themeTransmission)),
  http.get('/api/v2/read/strong', () => ok(fixtures.strong)),
  http.get('/api/v2/read/sector-rotation', () => ok(fixtures.sectorRotation)),
  http.get('/api/v2/read/watch', () => ok(fixtures.watch)),
  http.get('/api/v2/read/quote-board', () => ok(fixtures.quoteBoard)),
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
    const url = new URL(request.url)
    const code = url.searchParams.get('code')
    const report = url.searchParams.get('report') ?? 'income'
    if (!code || !/^\d{6}$/.test(code)) return invalidParam('code 须为 6 位数字')
    if (code === '000002') return ok({ ...fixtures.financialsNullFields, report })
    if (code === '000003') return ok({ ...fixtures.financialsEmptyRows, report })
    if (code === '000004') return ok({ ...fixtures.financialsDateNull, report })
    return ok({ ...fixtures.financialsFull, report })
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

  // ───────── 管理端（92 用户管理 V2 化）─────────
  // 内存态可变副本：列表/创建/编辑/删除共享同一份，使「创建后列表出现新用户」可被测。
  // 初始管理员 id=1 / username='admin'，与前端「不能删自己 / 不能删初始 admin」规则同源。
  // 状态提升到模块作用域（供 resetAdminMock 在测试间复位，避免跨测试污染）。
  ...(() => {
    const api = adminMockState
    return [
      http.get('/api/admin/users', ({ request }) => {
        const url = new URL(request.url)
        const page = Number(url.searchParams.get('page') ?? '1') || 1
        const perPage = Math.min(200, Number(url.searchParams.get('per_page') ?? '50') || 50)
        const kw = (url.searchParams.get('keyword') ?? '').toLowerCase()
        const filtered = kw
          ? api.users.filter((u) => u.username.toLowerCase().includes(kw))
          : api.users
        const start = (page - 1) * perPage
        const items = filtered.slice(start, start + perPage)
        const total = filtered.length
        return ok({
          items,
          total,
          page,
          per_page: perPage,
          pages: Math.max(1, Math.ceil(total / perPage)),
        })
      }),
      http.post('/api/admin/users', async ({ request }) => {
        const body = (await request.json().catch(() => ({}))) as {
          username?: string
          password?: string
          role?: string
        }
        const username = (body.username ?? '').trim()
        const password = body.password ?? ''
        const role = body.role === 'admin' ? 'admin' : 'user'
        if (!/^[a-zA-Z0-9_一-龥]{2,32}$/.test(username)) {
          return badRequest('用户名需 2-32 位，仅含字母数字下划线中文')
        }
        if (password.length < 6) return badRequest('密码至少 6 位')
        if (role !== 'admin' && role !== 'user') return badRequest('角色仅限 admin 或 user')
        if (api.users.some((u) => u.username === username)) return badRequest('用户名已存在')
        const user = {
          id: api.nextId++,
          username,
          role,
          created_at: MOCK_CREATED_AT,
          is_active: true,
          avatar: null,
          settings: {},
        }
        api.users.push(user)
        api.logs.unshift(makeLog(api, 'create_user', username, `role=${role}`))
        return ok(user, '创建成功')
      }),
      http.put('/api/admin/users/:id', async ({ request, params }) => {
        const id = Number(params.id)
        const user = api.users.find((u) => u.id === id)
        if (!user) return badRequest('资源不存在')
        const body = (await request.json().catch(() => ({}))) as {
          role?: string
          is_active?: boolean
          password?: string
        }
        const changes: string[] = []
        if (body.role !== undefined) {
          if (body.role !== 'admin' && body.role !== 'user') return badRequest('角色仅限 admin 或 user')
          user.role = body.role
          changes.push(`role=${body.role}`)
        }
        if (body.is_active !== undefined) {
          user.is_active = body.is_active
          changes.push(`is_active=${user.is_active}`)
        }
        if (body.password) {
          if (body.password.length < 6) return badRequest('密码至少 6 位')
          changes.push('password=***')
        }
        api.logs.unshift(makeLog(api, 'update_user', user.username, changes.join(', ')))
        return ok(user, '更新成功')
      }),
      http.delete('/api/admin/users/:id', ({ params }) => {
        const id = Number(params.id)
        const user = api.users.find((u) => u.id === id)
        if (!user) return badRequest('资源不存在')
        if (id === 1) return badRequest('不能删除初始管理员账号')
        api.users = api.users.filter((u) => u.id !== id)
        api.logs.unshift(makeLog(api, 'delete_user', user.username, ''))
        return ok(null, '删除成功')
      }),
      http.get('/api/admin/logs', ({ request }) => {
        const url = new URL(request.url)
        const page = Number(url.searchParams.get('page') ?? '1') || 1
        const perPage = Math.min(200, Number(url.searchParams.get('per_page') ?? '50') || 50)
        const start = (page - 1) * perPage
        const items = api.logs.slice(start, start + perPage)
        const total = api.logs.length
        return ok({
          items,
          total,
          page,
          per_page: perPage,
          pages: Math.max(1, Math.ceil(total / perPage)),
        })
      }),
    ]
  })(),
]

function makeLog(api: AdminMockState, action: string, target: string, detail: string) {
  return {
    id: api.nextLogId++,
    user_id: 1,
    username: 'admin',
    action,
    target,
    detail,
    created_at: MOCK_CREATED_AT,
  }
}

/** 测试间复位管理端 Mock 状态，避免跨测试污染（创建/删除在内存态累积）。 */
export function resetAdminMock(): void {
  adminMockState.users = fixtures.adminUsers.map((u) => ({ ...u }))
  adminMockState.logs = fixtures.adminLogs.map((l) => ({ ...l }))
  adminMockState.nextId = Math.max(0, ...fixtures.adminUsers.map((u) => u.id)) + 1
  adminMockState.nextLogId = Math.max(0, ...fixtures.adminLogs.map((l) => l.id)) + 1
}
