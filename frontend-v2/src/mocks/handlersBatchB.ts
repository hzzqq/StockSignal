import { http } from 'msw'
import {
  breadthDivergenceFixture,
  temperatureBacktestFullFixture,
  userDashboardFixture,
  reviewNotesFixture,
} from './fixturesBatchB'
import { writeOk, writeBadRequest, writeNotFound } from './writeEnvelope'
import * as fixtures from './fixtures'
import {
  USER_DASHBOARD_WIDGET_KEYS,
  isValidCalendarDate,
  type ReviewNotesData,
} from '@/api/schemas/batchBWrite'

/**
 * parity B 批次 MSW 演示 handler。
 *
 * - 模块作用域可变状态：两个 PUT 真的改内存态，后续 GET 读到新值（resetBatchBMock 复位）；
 * - 非法 widgets / date / window_days → HTTP 422 + code=validation_error（writeBadRequest）；
 * - 同时同步 fixtures.userDashboard，使既有的 GET /api/v2/read/user-dashboard 也能读到新值，
 *   无论本 handler 数组与既有 handlers 的注册顺序如何都不产生「假成功」；
 * - 时间戳固定常量，禁止运行时 now 冒充数据日。
 */

const WIDGET_KEY_SET = new Set<string>(USER_DASHBOARD_WIDGET_KEYS)
const ORIGINAL_DASHBOARD_WIDGETS: string[] = [...fixtures.userDashboard.default_widgets]

interface BatchBMockState {
  widgets: string[]
  reviewNotes: Map<string, ReviewNotesData>
}

function initialState(): BatchBMockState {
  return {
    widgets: [...userDashboardFixture.widgets],
    reviewNotes: new Map<string, ReviewNotesData>([
      [reviewNotesFixture.date, { ...reviewNotesFixture }],
    ]),
  }
}

const state: BatchBMockState = initialState()

/** 测试间复位，避免两个 PUT 的内存态在用例之间累积造成跨测污染。 */
export function resetBatchBMock(): void {
  const fresh = initialState()
  state.widgets = fresh.widgets
  state.reviewNotes = fresh.reviewNotes
  fixtures.userDashboard.default_widgets = [...ORIGINAL_DASHBOARD_WIDGETS]
}

async function readBody(request: Request): Promise<Record<string, unknown>> {
  const raw = await request.json().catch(() => ({}))
  return raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {}
}

/** v2 页面真实白名单：snapshot/recommendation/breadth/event/backtest，1–5 项、不重复。 */
function validWidgets(v: unknown): v is string[] {
  if (!Array.isArray(v)) return false
  if (v.length < 1 || v.length > 5) return false
  if (!v.every((x) => typeof x === 'string' && WIDGET_KEY_SET.has(x))) return false
  return new Set(v).size === v.length
}

type ParamResult = { ok: true; value: number | null } | { ok: false }

/** window_days 可省略；后端 _bb_int 口径：正整数且 1~5000。 */
function parseWindowDays(raw: string | null): ParamResult {
  if (raw === null || raw === '') return { ok: true, value: null }
  if (!/^\d+$/.test(raw)) return { ok: false }
  const v = Number(raw)
  if (!Number.isInteger(v) || v < 1 || v > 5000) return { ok: false }
  return { ok: true, value: v }
}

/** 有界数值参数：给了就必须是 [min,max] 内的有限数（后端 _bb_float 口径）。 */
function parseBoundedNumber(raw: string | null, min: number, max: number): ParamResult {
  if (raw === null || raw === '') return { ok: true, value: null }
  const v = Number(raw)
  if (!Number.isFinite(v) || v < min || v > max) return { ok: false }
  return { ok: true, value: v }
}

export const batchBHandlers = [
  // ── GET：广度分化（非法查询参数 → 422） ──
  http.get('/api/v2/read/breadth-divergence', ({ request }) => {
    const url = new URL(request.url)
    const red = parseBoundedNumber(url.searchParams.get('red_thresh'), 0, 100)
    const ldq = parseBoundedNumber(url.searchParams.get('ld_quantile'), 0.01, 0.99)
    const win = parseWindowDays(url.searchParams.get('window_days'))
    if (!red.ok || !ldq.ok || !win.ok) {
      return writeBadRequest('查询参数非法：red_thresh / ld_quantile / window_days')
    }
    return writeOk(breadthDivergenceFixture)
  }),

  // ── GET：温度回测（非法 window_days → 422） ──
  http.get('/api/v2/read/temperature-backtest', ({ request }) => {
    const url = new URL(request.url)
    const win = parseWindowDays(url.searchParams.get('window_days'))
    if (!win.ok) return writeBadRequest('window_days 非法（须为 1~5000 的正整数）')
    return writeOk(temperatureBacktestFullFixture)
  }),

  // ── GET：看板偏好（读内存态，写后可见） ──
  http.get('/api/v2/read/user-dashboard', () =>
    writeOk({
      default_widgets: [...state.widgets],
    }),
  ),

  // ── GET：复盘笔记（读内存态；未保存过则如实 not_found） ──
  http.get('/api/v2/read/review-notes', ({ request }) => {
    const date = new URL(request.url).searchParams.get('date') ?? ''
    if (!isValidCalendarDate(date)) return writeBadRequest('date 非法（须为真实 YYYY-MM-DD）')
    const note = state.reviewNotes.get(date)
    if (!note) return writeNotFound(`review_notes_${date}.md`)
    return writeOk(note)
  }),

  // ── PUT：看板偏好写（非法 widgets → 422，真改内存态） ──
  http.put('/api/v2/read/user-dashboard', async ({ request }) => {
    const body = await readBody(request)
    if (!validWidgets(body.widgets)) {
      return writeBadRequest('widgets 须为 1–5 个合法且不重复的组件 id')
    }
    const widgets: string[] = [...body.widgets]
    state.widgets = widgets
    // 同步既有夹具，让 handlers.ts 的 GET 也读到新值（顺序无关）
    fixtures.userDashboard.default_widgets = widgets
    return writeOk({ widgets: [...widgets] }, '看板偏好已保存')
  }),

  // ── PUT：复盘笔记写（非法 date → 422，真改内存态） ──
  http.put('/api/v2/read/review-notes', async ({ request }) => {
    const body = await readBody(request)
    const date = typeof body.date === 'string' ? body.date : ''
    if (!isValidCalendarDate(date)) return writeBadRequest('date 非法（须为真实 YYYY-MM-DD）')
    if (typeof body.content !== 'string' || body.content.length > 500000) {
      return writeBadRequest('content 须为 ≤500000 字符的字符串')
    }
    const note: ReviewNotesData = { date, content: body.content }
    state.reviewNotes.set(date, note)
    return writeOk(note, '复盘笔记已保存')
  }),
]
