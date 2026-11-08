/**
 * W4-B · 深链参数归一（纯函数，路由与单测共用）。
 *
 * 这是解决 E2E 范式冲突的关键：validateSearch 与纯函数单测都调这里，
 * 页面纯组件不依赖 RouterProvider 也能被 <Providers> 独立渲染。
 *
 * 真值依据：
 *  - 旧 24 页分段值「⚡ 快速选取 / 🔬 深度分析」(pages/24_个股研究.py:37-40)；
 *  - 旧 22 页只带 pick_stock、不带 hub_gyj_view 的跳转 (pages/22_基本面分析.py:864-866) → view=quick；
 *  - IA-MIGRATION.md §3.2 把「只带 pick_stock」一律映射 deep 属规划态错误，已更正。
 *
 * 诚实红线：view 缺/非法 → 明确常量 'quick'；code 非 6 位 → 不写 code 键，
 * 禁 `?? ''` / `?? 0` 兜底（空串会伪装成合法输入）。
 */
export type ResearchView = 'quick' | 'deep'

/** 归一后的深链结果（view 必有值，code 可缺省）。 */
export type ResearchSearch = {
  view: ResearchView
  code?: string
}

/** 路由 validateSearch 的输出类型：全字段 optional，避免 AppShell 泛化 <Link> 因 search 必填而 tsc 失败。 */
export type ResearchRouteSearch = { view?: ResearchView; code?: string }

const CODE_RE = /^\d{6}$/

function pickCode(raw: unknown): string | undefined {
  return typeof raw === 'string' && CODE_RE.test(raw) ? raw : undefined
}

function withCode(view: ResearchView, code: string | undefined): ResearchSearch {
  return code === undefined ? { view } : { view, code }
}

/** /stock/research?view=...&code=... → 归一。缺/非法 view → quick；code 非 6 位 → 不写键。 */
export function resolveResearchSearch(raw: Record<string, unknown>): ResearchSearch {
  const view: ResearchView = raw.view === 'deep' ? 'deep' : 'quick'
  return withCode(view, pickCode(raw.code))
}

/** /legacy?hub_gyj_view=...&pick_stock=... → 归一。
 *  旧链接真值是中文：'⚡ 快速选取'→quick、'🔬 深度分析'→deep（含 emoji）。
 *  只传 pick_stock 不带 hub_gyj_view → view=quick（旧 22:864-866 真值）。 */
export function resolveLegacySearch(raw: Record<string, unknown>): ResearchSearch {
  const v = raw.hub_gyj_view
  const view: ResearchView = v === '🔬 深度分析' || v === 'deep' ? 'deep' : 'quick'
  return withCode(view, pickCode(raw.pick_stock))
}

// ═══════════════════ W4-C · 多股对比深链（/stock/compare）══════════════════
// 与上面同范式：纯函数、路由 validateSearch 与单测共用；codes 逗号字符串在组件内解析，
// 故这里只负责把原始 search 归一成 {codes?: string[]; period?: string}。
// 诚实红线：非 6 位 code 过滤掉（不写进数组）；period 非 daily/weekly/monthly → undefined。

/** /stock/compare 归一后的深链结果（codes 为已过滤的 6 位码数组，可缺省）。 */
export type CompareRouteSearch = { codes?: string[]; period?: string }

const COMPARE_CODE_RE = /^\d{6}$/
const COMPARE_PERIODS = ['daily', 'weekly', 'monthly'] as const

/** ?codes=600519,000001&period=daily → {codes:['600519','000001'], period:'daily'}。 */
export function resolveCompareSearch(raw: Record<string, unknown>): CompareRouteSearch {
  const codesRaw = raw.codes
  let codes: string[] | undefined
  if (typeof codesRaw === 'string') {
    const arr = Array.from(
      new Set(
        codesRaw
          .split(',')
          .map((s) => s.trim())
          .filter((c) => COMPARE_CODE_RE.test(c)),
      ),
    )
    if (arr.length > 0) codes = arr
  }
  const periodRaw = raw.period
  const period =
    typeof periodRaw === 'string' && (COMPARE_PERIODS as readonly string[]).includes(periodRaw)
      ? periodRaw
      : undefined
  const out: CompareRouteSearch = {}
  if (codes) out.codes = codes
  if (period) out.period = period
  return out
}
