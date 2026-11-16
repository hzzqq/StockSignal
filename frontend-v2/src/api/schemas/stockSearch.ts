import { z } from 'zod'

/**
 * GET /api/stocks/search 的 v2 契约。
 * 后端返回 `Stock.to_dict()` + `score`；股票池兜底模块返回完全相同的结构。
 * 字段一律严格校验，缺字段/类型不符即抛错，绝不在 UI 层 `?? 默认值` 兜底。
 */
export const StockSearchItemSchema = z.object({
  code: z.string().min(1),
  name: z.string().min(1),
  market: z.string().nullable().optional(),
  asset_type: z.string().nullable().optional(),
  pinyin_initials: z.string().nullable().optional(),
  pinyin_full: z.string().nullable().optional(),
  score: z.number().optional(),
})
export type StockSearchItem = z.infer<typeof StockSearchItemSchema>

export const StockSearchResultSchema = z.array(StockSearchItemSchema)
export type StockSearchResult = z.infer<typeof StockSearchResultSchema>

/** v1 `search_ui._match_label` 的 v2 等价：单一真理源，UI 与测试共用，禁止靠文案猜。 */
export type StockMatchKind =
  | 'code_exact'
  | 'code_prefix'
  | 'name_exact'
  | 'name_prefix'
  | 'initials'
  | 'full_pinyin'
  | 'name_contains'
  | 'other'

export const STOCK_MATCH_LABEL: Record<StockMatchKind, string> = {
  code_exact: '代码精确',
  code_prefix: '代码前缀',
  name_exact: '名称精确',
  name_prefix: '名称前缀',
  initials: '拼音首字母',
  full_pinyin: '拼音全拼',
  name_contains: '名称包含',
  other: '匹配',
}

/** 按 v1 优先级判定匹配方式；仅用于展示标签，不参与召回与排序。 */
export function stockMatchKind(
  q: string,
  item: Pick<StockSearchItem, 'code' | 'name' | 'pinyin_initials' | 'pinyin_full'>,
): StockMatchKind {
  const s = q.trim().toLowerCase()
  if (!s) return 'other'
  const code = (item.code ?? '').toLowerCase()
  const name = (item.name ?? '').toLowerCase()
  const pi = (item.pinyin_initials ?? '').toLowerCase()
  const pf = (item.pinyin_full ?? '').toLowerCase()
  if (code === s) return 'code_exact'
  if (code.startsWith(s)) return 'code_prefix'
  if (name === s) return 'name_exact'
  if (name.startsWith(s)) return 'name_prefix'
  if (pi === s) return 'initials'
  if (pf === s || pf.startsWith(s)) return 'full_pinyin'
  if (name.includes(s)) return 'name_contains'
  if (pi.includes(s) || pf.includes(s)) return 'initials'
  return 'other'
}
