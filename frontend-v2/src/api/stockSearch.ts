import { apiFetch } from './client'
import { StockSearchResultSchema, type StockSearchResult } from './schemas/stockSearch'

/**
 * 股票搜索（代码 / 名称 / 拼音首字母 / 拼音全拼）。
 *
 * 对齐 v1 `modules/search_ui.py::_search_via_backend` 的后端口径，但前端一律走 v2
 * 的 `apiFetch` + Zod 严格校验：空查询不发请求，响应结构不符直接抛错，
 * 不把 `[]` 与「接口失败」混为一谈。
 */
export async function getStockSearch(q: string, limit = 10): Promise<StockSearchResult> {
  const query = q.trim()
  if (!query) return []
  const capped = Math.max(1, Math.min(50, Math.trunc(limit)))
  const data = await apiFetch<unknown>(
    `/stocks/search?q=${encodeURIComponent(query)}&limit=${capped}`,
  )
  return StockSearchResultSchema.parse(data)
}
