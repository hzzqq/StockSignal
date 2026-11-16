import { http } from 'msw'
import {
  writeOk,
  writeBadRequest,
  writeForbidden,
  writeNotFound,
  MOCK_WRITE_TS,
} from './writeEnvelope'
import {
  initialPriceAlerts,
  initialMarketAlerts,
  initialConfig,
  initialRuntimeOverrides,
} from './fixturesAlertWrite'
import type { PriceAlert, MarketAlert, AlertType } from '@/api/schemas/alertWrite'

/**
 * 价格预警 / 市场告警 写端点 MSW 演示态（与 handlers.ts 的 resetAdminMock 同范式）。
 *
 * 模块作用域可变状态实现「真实 CRUD」：创建→列表出现、toggle→active 取反、
 * 删除→消失、已读→unread_count 下降、扫描→列表新增。
 *
 * 后端校验规则逐条复刻（alert_routes.py L45-101）：缺 target_price / pattern_name /
 * volume_ratio / keyword → HTTP 422 + validation_error，绝不静默成功。
 * scan / config 为 @admin_required：非管理员返回 403 + forbidden 信封，绝不静默成功。
 *
 * ⚠️ 只导出 alertWriteHandlers，不写 handlers.ts 的 push；由 team-lead 统一接线。
 */

interface AlertWriteState {
  priceAlerts: PriceAlert[]
  marketAlerts: MarketAlert[]
  /** 模拟 User.settings.last_seen_market_alert；null 表示从未读 → 全部未读。 */
  lastSeen: string | null
  config: Record<string, unknown>
  runtimeOverrides: Record<string, unknown>
  nextPriceId: number
  nextMarketId: number
}

function makeState(): AlertWriteState {
  return {
    priceAlerts: initialPriceAlerts.map((a) => ({ ...a })),
    marketAlerts: initialMarketAlerts.map((a) => ({ ...a })),
    lastSeen: null,
    config: { ...initialConfig },
    runtimeOverrides: { ...initialRuntimeOverrides },
    nextPriceId: Math.max(0, ...initialPriceAlerts.map((a) => a.id)) + 1,
    nextMarketId: Math.max(0, ...initialMarketAlerts.map((a) => a.id)) + 1,
  }
}

// 复位只重新赋值模块变量：各 handler 闭包引用的是变量本身，下一次请求即读到新状态。
let state = makeState()

/** 测试间复位，避免创建/删除/已读在内存态跨用例累积。 */
export function resetAlertWriteMock(): void {
  state = makeState()
}

/**
 * 从 localStorage('ss_user') 读当前角色，与 src/lib/auth.ts::getCurrentUser 同源。
 * 这样「前端按钮门控」与「后端鉴权拦截」在测试里由同一份 ss_user 驱动。
 * 读不到 / 解析失败一律返回 null（无权限），安全默认。
 */
function currentRole(): 'admin' | 'user' | null {
  try {
    const raw = globalThis.localStorage?.getItem('ss_user')
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    const role = (parsed as { role?: unknown } | null)?.role
    return role === 'admin' || role === 'user' ? role : null
  } catch {
    return null
  }
}

const ALERT_TYPES: readonly string[] = ['price', 'pattern', 'volume', 'announcement']

function parseIntParam(raw: string | null, fallback: number, lo: number, hi: number): number {
  if (raw === null) return fallback
  const n = Number(raw)
  if (!Number.isFinite(n) || n < lo) return fallback
  return Math.min(hi, Math.trunc(n))
}

function byCreatedDesc(a: MarketAlert, b: MarketAlert): number {
  const av = a.created_at === null ? '' : a.created_at
  const bv = b.created_at === null ? '' : b.created_at
  return bv.localeCompare(av)
}

export const alertWriteHandlers = [
  // ───────── 价格预警 ─────────
  http.get('/api/price-alerts', () => writeOk(state.priceAlerts)),

  // 创建：逐条复刻后端四类必填校验，缺参一律 422 validation_error。
  http.post('/api/price-alerts', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const code = String(body.stock_code === undefined ? '' : body.stock_code).trim()
    const alertType = String(body.alert_type === undefined ? 'price' : body.alert_type)
      .trim()
      .toLowerCase()
    if (code.length === 0) return writeBadRequest('股票代码不能为空')
    if (!ALERT_TYPES.includes(alertType)) {
      return writeBadRequest('alert_type 只能是 price/pattern/volume/announcement')
    }

    const name = String(body.stock_name === undefined ? '' : body.stock_name).trim()
    const condition = String(body.condition === undefined ? 'above' : body.condition)
      .trim()
      .toLowerCase()
    let target = 0
    let paramsJson: string | null = null

    if (alertType === 'price') {
      const raw = body.target_price
      const n = typeof raw === 'number' ? raw : Number(raw)
      if (!Number.isFinite(n)) return writeBadRequest('目标价格必须是数字')
      target = n
      if (condition !== 'above' && condition !== 'below') {
        return writeBadRequest('condition 只能是 above 或 below')
      }
      if (target <= 0) return writeBadRequest('目标价格必须大于 0')
    } else {
      const rawParams = (body.params === undefined ? {} : body.params) as Record<string, unknown>
      if (alertType === 'pattern') {
        const pname = String(rawParams.pattern_name === undefined ? '' : rawParams.pattern_name).trim()
        if (pname.length === 0) return writeBadRequest('形态预警需指定 pattern_name')
        paramsJson = JSON.stringify({ pattern_name: pname })
      } else if (alertType === 'volume') {
        const rawVr = rawParams.volume_ratio
        const vr = typeof rawVr === 'number' ? rawVr : Number(rawVr)
        if (!Number.isFinite(vr)) return writeBadRequest('成交量异动预警需指定 volume_ratio（数字）')
        if (vr <= 0) return writeBadRequest('volume_ratio 必须大于 0')
        paramsJson = JSON.stringify({ volume_ratio: vr })
      } else {
        const kw = String(rawParams.keyword === undefined ? '' : rawParams.keyword).trim()
        if (kw.length === 0) return writeBadRequest('公告预警需指定 keyword')
        paramsJson = JSON.stringify({ keyword: kw })
      }
    }

    const alert: PriceAlert = {
      id: state.nextPriceId++,
      user_id: 1,
      stock_code: code,
      stock_name: name,
      alert_type: alertType as AlertType,
      condition: condition === 'below' ? 'below' : 'above',
      target_price: target,
      params: paramsJson,
      active: true,
      triggered: false,
      triggered_at: null,
      created_at: MOCK_WRITE_TS,
    }
    // 后端按 created_at desc 排序；新建固定戳，用「最新在前」表现。
    state.priceAlerts = [alert, ...state.priceAlerts]
    return writeOk(alert, '预警创建成功')
  }),

  http.put('/api/price-alerts/:id/toggle', ({ params }) => {
    const id = Number(params.id)
    const found = state.priceAlerts.find((a) => a.id === id)
    if (!found) return writeNotFound(`预警 ${id}`)
    const updated: PriceAlert = { ...found, active: !found.active }
    state.priceAlerts = state.priceAlerts.map((a) => (a.id === id ? updated : a))
    return writeOk(updated, '状态已更新')
  }),

  http.delete('/api/price-alerts/:id', ({ params }) => {
    const id = Number(params.id)
    if (!state.priceAlerts.some((a) => a.id === id)) return writeNotFound(`预警 ${id}`)
    state.priceAlerts = state.priceAlerts.filter((a) => a.id !== id)
    return writeOk(null, '预警已删除')
  }),

  // ───────── 市场指标异动提醒 ─────────
  http.get('/api/market-alerts', ({ request }) => {
    const u = new URL(request.url)
    const unreadOnly = u.searchParams.get('unread_only') === '1'
    const limit = parseIntParam(u.searchParams.get('limit'), 50, 1, 200)
    const offset = parseIntParam(u.searchParams.get('offset'), 0, 0, Number.MAX_SAFE_INTEGER)
    const lastSeen = state.lastSeen
    const isUnread = (m: MarketAlert): boolean => {
      if (lastSeen === null) return true
      return m.created_at !== null && m.created_at > lastSeen
    }
    const sorted = [...state.marketAlerts].sort(byCreatedDesc)
    const filtered = unreadOnly ? sorted.filter(isUnread) : sorted
    const items = filtered.slice(offset, offset + limit)
    return writeOk({
      items,
      unread_count: state.marketAlerts.filter(isUnread).length,
      total: state.marketAlerts.length,
      last_seen: lastSeen,
    })
  }),

  http.post('/api/market-alerts/:id/read', ({ params }) => {
    const id = Number(params.id)
    const found = state.marketAlerts.find((m) => m.id === id)
    if (!found) return writeNotFound(`告警 ${id}`)
    const lastSeen = state.lastSeen
    if (found.created_at !== null && (lastSeen === null || found.created_at > lastSeen)) {
      state.lastSeen = found.created_at
    }
    return writeOk(null, '已标记为已读')
  }),

  http.post('/api/market-alerts/read-all', () => {
    // 后端用 utc_now() 推进 last_seen；演示态用「现有告警最大 created_at」确定性推进，
    // 使 unread_count 归零，绝不 new Date()。
    let latest = state.lastSeen
    for (const m of state.marketAlerts) {
      if (m.created_at !== null && (latest === null || m.created_at > latest)) latest = m.created_at
    }
    state.lastSeen = latest
    return writeOk(null, '已全部标记为已读')
  }),

  // @admin_required：非管理员 403，不静默成功。
  http.post('/api/market-alerts/scan', () => {
    if (currentRole() !== 'admin') return writeForbidden()
    const created: MarketAlert = {
      id: state.nextMarketId++,
      metric_key: 'scan',
      metric_name: '手动扫描',
      severity: 'info',
      message: '管理员手动触发一次扫描（演示，新增 1 条样例告警）',
      value: null,
      threshold: null,
      created_at: '2026-01-01T12:00:00Z',
    }
    state.marketAlerts = [created, ...state.marketAlerts]
    return writeOk({ inserted: 1 }, '扫描完成，新增 1 条')
  }),

  // @admin_required
  http.get('/api/market-alerts/config', () => {
    if (currentRole() !== 'admin') return writeForbidden()
    return writeOk({ config: state.config, runtime_overrides: state.runtimeOverrides })
  }),

  // @admin_required：合并运行时覆盖，返回合并后的 config。
  http.post('/api/market-alerts/config', async ({ request }) => {
    if (currentRole() !== 'admin') return writeForbidden()
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    state.runtimeOverrides = { ...state.runtimeOverrides, ...body }
    state.config = { ...state.config, ...body }
    return writeOk({ config: state.config }, '扫描策略已更新（运行时生效）')
  }),
]
