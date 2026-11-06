import { http, HttpResponse } from 'msw'
import * as fixtures from './fixtures'

/** 统一成功信封（对齐 backend/utils/response.py ok()）。 */
function ok(data: unknown, message = 'ok') {
  return HttpResponse.json({ status: 'ok', code: 0, message, data })
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
]
