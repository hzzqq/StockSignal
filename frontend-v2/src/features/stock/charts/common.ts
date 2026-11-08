import { CHART } from '@/shared/charts/palette'

/**
 * 页面级价格域（A 股双套语义）。
 *
 * DESIGN.md §3 要求「所有显示涨跌的组件必须显式传 `priceDomain="market" | "report"`，
 * 不设默认值——缺省即编译报错」，故此处定义类型且**不提供默认值**，由调用点显式声明。
 *
 *  - market：交易屏 / 行情看板口径 → 涨红跌绿（--ss-up / --ss-down）
 *  - report：报告体 / 个股页价格域口径 → 涨绿跌红（--doc-up / --doc-down）
 *
 * 个股研究页（/stock/research）取 **report**，依据：
 *  - frontend-v2/DESIGN.md §2 表：「报告体价格域 → doc-up / doc-down → 报告页/个股页（绿涨红跌）」；
 *  - docs/frontend-v2/DESIGN.md §3 表与 §6.2：「个股页价格域 → doc-up/doc-down」、
 *    「K线阴阳线：按 priceDomain 注入，报告体页面不得沿用交易屏红涨绿跌」；
 *  - src/styles/tokens.css 头注：「doc-* 报告体 / 个股页语义：涨=绿、跌=红（与交易屏相反）」；
 *  - v1 个股页实证：modules/stock_research.py:65,71 用 up_color=RED(#009e60 绿) / down_color=GREEN(#dc2626 红)，
 *    且 :429 脚注明写「虚线为昨收。绿涨红跌。」；pages/96_新手教程.py:202,240 对用户口径同样是
 *    「个股分析页（报告体）的『价格域』为文档体绿涨红跌例外」。
 */
export type PriceDomain = 'market' | 'report'

/**
 * canvas 方向色（ECharts 吃字面 hex，不能用 var()）。
 * 注意 docDown 与 up 同为 #ff4d4f（双语义同源，见 theme-contrast.test.ts「docDown === up」），
 * docUp #009e60 与 ss-down #00d486 不同绿，remapChartColors 按 hex 映射到亮色主题对应值。
 */
export const DIRECTION_HEX: Record<PriceDomain, { up: string; down: string }> = {
  market: { up: CHART.up, down: CHART.down },
  report: { up: CHART.docUp, down: CHART.docDown },
}

/**
 * DOM 方向墨色（CSS 变量别名）。
 * 用 var() 而非 --color-* 直连：tokens.css 明确这些 ink 别名「仅供图表/内联样式以 var() 消费」。
 */
export const DIRECTION_INK: Record<PriceDomain, { up: string; down: string }> = {
  market: { up: 'var(--ss-up-ink)', down: 'var(--ss-down-ink)' },
  report: { up: 'var(--doc-up-ink)', down: 'var(--doc-down-ink)' },
}

/** 只接受有限数字：null / NaN / Infinity / 非数值一律视为缺失（绝不补 0）。 */
export function toFiniteNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}
