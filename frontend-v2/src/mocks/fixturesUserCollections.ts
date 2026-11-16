import { z } from 'zod'
import {
  WatchlistItemSchema,
  JunkStockItemSchema,
  UserScoreSchema,
  BatchResultSchema,
  AddItemResultSchema,
  WatchlistBatchDeleteResultSchema,
  JunkBatchDeleteResultSchema,
  type WatchlistItem,
  type JunkStockItem,
  type UserScore,
  type BatchResult,
  type AddItemResult,
  type WatchlistBatchDeleteResult,
  type JunkBatchDeleteResult,
} from '@/api/schemas/userCollections'

/**
 * 用户三组写能力 · MSW 演示夹具。
 *
 * 结构必须与真后端逐字段一致（见 config_routes.py / stock_tag_routes.py / models.py）；
 * 数值是演示值，字段形状不得臆造。固定时间戳字符串，不用 new Date() 冒充数据日
 * （honest-data 守卫会真扫全 src）。
 */
const FIXTURE_TS = '2026-01-01T08:00:00Z'

export const watchlistFixture: WatchlistItem[] = [
  { id: 1, stock_code: '600519', stock_name: '贵州茅台', note: '核心持仓', created_at: FIXTURE_TS },
  { id: 2, stock_code: '000001', stock_name: '平安银行', note: null, created_at: FIXTURE_TS },
]

export const junkStocksFixture: JunkStockItem[] = [
  { id: 11, stock_code: '000002', stock_name: '万科A', note: '回避', created_at: FIXTURE_TS },
]

export const userScoresFixture: UserScore[] = [
  { id: 21, user_id: 1, stock_code: '600519', stock_name: '贵州茅台', score: 88, updated_at: FIXTURE_TS },
]

export const addItemResultFixture: AddItemResult = { id: 3, stock_code: '600519' }

export const batchResultFixture: BatchResult = {
  added: ['600519'],
  skipped: ['000001'],
  failed: [{ code: '', reason: '股票代码不能为空' }],
}

export const watchlistBatchDeleteFixture: WatchlistBatchDeleteResult = {
  deleted: ['600519'],
  forbidden: [{ code: '000001', reason: '无权限访问' }],
  not_found: ['999999'],
}

export const junkBatchDeleteFixture: JunkBatchDeleteResult = { deleted: [11] }

/**
 * 契约漂移守卫 A 段用（tests/unit/contract-drift.test.ts 由 team-lead 统一接线）。
 * 每个夹具对象用对应 Zod schema 严格 parse，锁定「mock ↔ 契约自洽」；
 * 含空数组 / null / 空态变体，防止「只给满数据」掩盖契约里的可空字段。
 */
export const userCollectionsFixturePairs: Array<{
  name: string
  schema: z.ZodTypeAny
  samples: unknown[]
}> = [
  {
    name: 'user-collections/watchlist',
    schema: z.array(WatchlistItemSchema),
    samples: [watchlistFixture, []],
  },
  {
    name: 'user-collections/junk-stocks',
    schema: z.array(JunkStockItemSchema),
    samples: [junkStocksFixture, []],
  },
  {
    name: 'user-collections/user-scores',
    schema: z.array(UserScoreSchema),
    samples: [userScoresFixture, []],
  },
  {
    name: 'user-collections/user-score-single',
    schema: UserScoreSchema.nullable(),
    samples: [userScoresFixture[0], null],
  },
  {
    name: 'user-collections/add-item-result',
    schema: AddItemResultSchema.nullable(),
    samples: [addItemResultFixture, null],
  },
  {
    name: 'user-collections/batch-result',
    schema: BatchResultSchema,
    samples: [batchResultFixture],
  },
  {
    name: 'user-collections/watchlist-batch-delete',
    schema: WatchlistBatchDeleteResultSchema,
    samples: [watchlistBatchDeleteFixture],
  },
  {
    name: 'user-collections/junk-batch-delete',
    schema: JunkBatchDeleteResultSchema,
    samples: [junkBatchDeleteFixture],
  },
]
