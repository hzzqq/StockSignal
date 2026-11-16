import { http } from 'msw'
import {
  watchlistFixture,
  junkStocksFixture,
  userScoresFixture,
} from './fixturesUserCollections'
import {
  writeOk,
  writeBadRequest,
  writeNotFound,
  MOCK_WRITE_TS,
} from './writeEnvelope'
import type { WatchlistItem, JunkStockItem, UserScore } from '@/api/schemas/userCollections'

/**
 * 用户三组写能力 · MSW 演示 handler（对齐 backend/api/config_routes.py、
 * backend/api/stock_tag_routes.py）。
 *
 * - 模块作用域可变状态：创建 / 删除真实改内存态，随后 GET 能读到新项（不做假成功）；
 * - 用 writeOk / writeBadRequest / writeNotFound / MOCK_WRITE_TS 统一信封与演示时间戳；
 * - 非法入参一律返回 400（validation_error），绝不静默接受；
 * - 固定路径（/batch）必须注册在动态路径（/:id）之前，否则 'batch' 会被当成 id。
 */

interface UserCollectionsMockState {
  watchlist: WatchlistItem[]
  junkStocks: JunkStockItem[]
  userScores: UserScore[]
  nextWatchId: number
  nextJunkId: number
  nextScoreId: number
}

function initialState(): UserCollectionsMockState {
  return {
    watchlist: watchlistFixture.map((w) => ({ ...w })),
    junkStocks: junkStocksFixture.map((j) => ({ ...j })),
    userScores: userScoresFixture.map((s) => ({ ...s })),
    nextWatchId: Math.max(0, ...watchlistFixture.map((w) => w.id)) + 1,
    nextJunkId: Math.max(0, ...junkStocksFixture.map((j) => j.id)) + 1,
    nextScoreId: Math.max(0, ...userScoresFixture.map((s) => s.id)) + 1,
  }
}

const state: UserCollectionsMockState = initialState()

/** 测试间复位，避免创建 / 删除在内存态累积造成跨用例污染。 */
export function resetUserCollectionsMock(): void {
  const fresh = initialState()
  state.watchlist = fresh.watchlist
  state.junkStocks = fresh.junkStocks
  state.userScores = fresh.userScores
  state.nextWatchId = fresh.nextWatchId
  state.nextJunkId = fresh.nextJunkId
  state.nextScoreId = fresh.nextScoreId
}

async function readBody(request: Request): Promise<Record<string, unknown>> {
  const raw = await request.json().catch(() => ({}))
  return raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {}
}

export const userCollectionsHandlers = [
  // ───────────────────────── 自选股 ─────────────────────────
  http.get('/api/watchlist', () => writeOk(state.watchlist)),

  http.post('/api/watchlist', async ({ request }) => {
    const body = await readBody(request)
    const code = typeof body.stock_code === 'string' ? body.stock_code.trim() : ''
    if (!code) return writeBadRequest('股票代码不能为空')
    if (state.watchlist.some((w) => w.stock_code === code)) {
      // 真后端：已存在时 message="已在自选股中"、data=null（status 仍为 ok）
      return writeOk(null, '已在自选股中')
    }
    const item: WatchlistItem = {
      id: state.nextWatchId++,
      stock_code: code,
      stock_name: code, // 无股票池查询，按后端 fallback 用代码兜底，不臆造名称
      note: typeof body.note === 'string' ? body.note : null,
      created_at: MOCK_WRITE_TS,
    }
    state.watchlist.push(item)
    return writeOk({ id: item.id, stock_code: item.stock_code }, '添加成功')
  }),

  // 固定路径必须先于 /:id 注册
  http.post('/api/watchlist/batch', async ({ request }) => {
    const body = await readBody(request)
    if (!Array.isArray(body.codes) || body.codes.length === 0) {
      return writeBadRequest('codes 不能为空且须为数组')
    }
    const note = typeof body.note === 'string' ? body.note : null
    const added: string[] = []
    const skipped: string[] = []
    const failed: Array<{ code: string; reason: string }> = []
    for (const raw of body.codes) {
      const code = typeof raw === 'string' ? raw.trim() : ''
      if (!code) {
        failed.push({ code: String(raw), reason: '股票代码不能为空' })
        continue
      }
      if (state.watchlist.some((w) => w.stock_code === code)) {
        skipped.push(code)
        continue
      }
      state.watchlist.push({
        id: state.nextWatchId++,
        stock_code: code,
        stock_name: code,
        note,
        created_at: MOCK_WRITE_TS,
      })
      added.push(code)
    }
    return writeOk({ added, skipped, failed }, '批量添加完成')
  }),

  http.delete('/api/watchlist/batch', async ({ request }) => {
    const body = await readBody(request)
    const ids = Array.isArray(body.ids) ? body.ids : null
    const codes = Array.isArray(body.codes) ? body.codes : null
    if ((ids === null || ids.length === 0) && (codes === null || codes.length === 0)) {
      return writeBadRequest('ids 或 codes 至少提供一个数组')
    }
    const deleted: string[] = []
    // 单用户演示态无「他人项」，forbidden 恒为空数组（如实，不臆造越权结果）
    const forbidden: Array<{ code: string; reason: string }> = []
    const notFound: string[] = []
    if (ids !== null && ids.length > 0) {
      for (const itemId of ids) {
        const idx = state.watchlist.findIndex((w) => w.id === Number(itemId))
        if (idx === -1) {
          notFound.push(String(itemId))
          continue
        }
        deleted.push(state.watchlist[idx].stock_code)
        state.watchlist.splice(idx, 1)
      }
    } else if (codes !== null) {
      for (const raw of codes) {
        const code = typeof raw === 'string' ? raw.trim() : ''
        if (!code) continue
        const idx = state.watchlist.findIndex((w) => w.stock_code === code)
        if (idx === -1) {
          notFound.push(code)
          continue
        }
        deleted.push(code)
        state.watchlist.splice(idx, 1)
      }
    }
    return writeOk({ deleted, forbidden, not_found: notFound }, '批量删除完成')
  }),

  http.delete('/api/watchlist/:id', ({ params }) => {
    const idx = state.watchlist.findIndex((w) => w.id === Number(params.id))
    if (idx === -1) return writeNotFound('自选股')
    state.watchlist.splice(idx, 1)
    return writeOk(null, '移除成功')
  }),

  // ───────────────────────── 垃圾股 ─────────────────────────
  http.get('/api/junk-stocks', () => writeOk(state.junkStocks)),

  http.post('/api/junk-stocks', async ({ request }) => {
    const body = await readBody(request)
    const code = typeof body.stock_code === 'string' ? body.stock_code.trim() : ''
    if (!code) return writeBadRequest('股票代码不能为空')
    if (state.junkStocks.some((j) => j.stock_code === code)) {
      return writeOk(null, '已在垃圾股中')
    }
    const item: JunkStockItem = {
      id: state.nextJunkId++,
      stock_code: code,
      stock_name: code,
      note: typeof body.note === 'string' ? body.note : null,
      created_at: MOCK_WRITE_TS,
    }
    state.junkStocks.push(item)
    return writeOk({ id: item.id, stock_code: item.stock_code }, '添加成功')
  }),

  http.delete('/api/junk-stocks/batch', async ({ request }) => {
    const body = await readBody(request)
    if (!Array.isArray(body.ids) || body.ids.length === 0) {
      return writeBadRequest('ids 不能为空且须为数组')
    }
    const deleted: number[] = []
    for (const itemId of body.ids) {
      const idx = state.junkStocks.findIndex((j) => j.id === Number(itemId))
      if (idx === -1) continue
      deleted.push(Number(itemId))
      state.junkStocks.splice(idx, 1)
    }
    return writeOk({ deleted }, '批量移除成功')
  }),

  http.delete('/api/junk-stocks/:id', ({ params }) => {
    const idx = state.junkStocks.findIndex((j) => j.id === Number(params.id))
    if (idx === -1) return writeNotFound('垃圾股')
    state.junkStocks.splice(idx, 1)
    return writeOk(null, '移除成功')
  }),

  // ───────────────────────── 用户自定义打分 ─────────────────────────
  http.get('/api/user-scores', () => writeOk(state.userScores)),

  http.get('/api/user-scores/:code', ({ params }) => {
    const code = String(params.code)
    const row = state.userScores.find((s) => s.stock_code === code)
    return writeOk(row ?? null)
  }),

  http.post('/api/user-scores', async ({ request }) => {
    const body = await readBody(request)
    const code = typeof body.stock_code === 'string' ? body.stock_code.trim() : ''
    if (!code) return writeBadRequest('股票代码不能为空')
    // 对齐后端 int(score)：接受数字与数字字符串，挡住空 / NaN / 非整数 / 越界
    const rawScore = body.score
    const score = typeof rawScore === 'string' && rawScore.trim() === '' ? NaN : Number(rawScore)
    if (
      rawScore === null ||
      rawScore === undefined ||
      !Number.isFinite(score) ||
      !Number.isInteger(score)
    ) {
      return writeBadRequest('分数须为整数')
    }
    if (score < 0 || score > 100) return writeBadRequest('分数须在 0–100 之间')

    const name = typeof body.stock_name === 'string' ? body.stock_name.trim() : ''
    const existing = state.userScores.find((s) => s.stock_code === code)
    if (existing) {
      existing.score = score
      if (name) existing.stock_name = name
      existing.updated_at = MOCK_WRITE_TS
      return writeOk({ ...existing }, '评分已保存')
    }
    const row: UserScore = {
      id: state.nextScoreId++,
      user_id: 1,
      stock_code: code,
      stock_name: name === '' ? code : name,
      score,
      updated_at: MOCK_WRITE_TS,
    }
    state.userScores.push(row)
    return writeOk({ ...row }, '评分已保存')
  }),

  http.delete('/api/user-scores/:code', ({ params }) => {
    const code = String(params.code)
    const idx = state.userScores.findIndex((s) => s.stock_code === code)
    if (idx !== -1) state.userScores.splice(idx, 1)
    // 真后端：不存在也返回 ok（仅 message）
    return writeOk(null, '评分已删除')
  }),
]
