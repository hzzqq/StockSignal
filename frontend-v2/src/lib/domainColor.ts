/**
 * 字段域级双色（纯函数，可单测）。
 *
 * A 股双套语义（与 src/styles/tokens.css、modules/colors.py 口径一致，历史红线）：
 *  - ss-*   交易屏 / 行情域：涨=红（--ss-up-ink）、跌=绿（--ss-down-ink）
 *  - doc-*  报告体 / 业绩域：涨=绿（--doc-up-ink）、跌=红（--doc-down-ink）
 * 两套装反色，不可混淆。
 *
 * 颜色仅作「域」区分 / 强弱信号，绝不代表「红绿即涨跌」的越权语义：
 * 涨跌方向由数值符号表达（见 inkForCell 的负值降级），与既有「🟢强势 / 🔴偏弱」
 * 信号灯语义一致；价格域是例外（交易屏本身即红涨绿跌，方向色即域色）。
 */

/** 价格/行情域关键词（精确匹配）。 */
const PRICE_SET = new Set<string>([
  'price',
  'change_pct',
  'pct_chg',
  'open',
  'high',
  'low',
  'pre_close',
  'volume',
  'amount',
  'pe',
  'pb',
  'ps',
  'market_cap',
  'turnover',
  'amplitude',
])

/** 价格/行情域前缀（技术指标）。注意 'ma' 仅匹配 ma+数字（ma5/ma10/ma20/ma60），
 *  不可裸写 'ma' 否则误伤 'margin'（业绩域）。macd/kdj/boll/rsi 作为前缀安全。 */
const PRICE_PREFIX = ['rsi', 'macd', 'kdj', 'boll']

/** 业绩/报告域关键词（精确匹配）。 */
const REPORT_SET = new Set<string>(['roe', 'margin', 'yoy'])

/** 业绩/报告域前缀。 */
const REPORT_PREFIX = ['revenue', 'profit', 'growth']

export type DomainKind = 'price' | 'report' | 'neutral'

/** 按字段名关键词判定域。大小写不敏感。 */
export function classifyDomain(field: string): DomainKind {
  const f = field.toLowerCase()
  const isPricePrefix =
    PRICE_PREFIX.some((p) => f.startsWith(p)) ||
    f === 'ma' ||
    /^ma\d+$/.test(f) // ma5/ma10/ma20/ma60，避免误伤 margin
  if (PRICE_SET.has(f) || isPricePrefix) return 'price'
  if (REPORT_SET.has(f) || REPORT_PREFIX.some((p) => f.startsWith(p))) return 'report'
  return 'neutral'
}

/**
 * 域级墨色：价格域返回交易屏 up 墨色（红），业绩域返回报告体 up 墨色（绿），
 * 未知域返回中性 --sf-ink。仅作域区分，不表达单值涨跌方向。
 */
export function domainInk(field: string): string {
  const d = classifyDomain(field)
  if (d === 'price') return 'var(--ss-up-ink)'
  if (d === 'report') return 'var(--doc-up-ink)'
  return 'var(--sf-ink)'
}

/**
 * 单元格墨色：在域色基础上，若值为负数则翻转到该域的「下挫」墨色
 * （价格域绿 / 报告体红）。保持 A 股双套语义，不越权伪造方向。
 * 非数字 / 缺值 → 沿用域 up 墨色（方向未知，不擅自标红绿）。
 */
export function inkForCell(field: string, value: unknown): string {
  const d = classifyDomain(field)
  if (d === 'neutral') return 'var(--sf-ink)'
  if (typeof value === 'number' && value < 0) {
    return d === 'price' ? 'var(--ss-down-ink)' : 'var(--doc-down-ink)'
  }
  return d === 'price' ? 'var(--ss-up-ink)' : 'var(--doc-up-ink)'
}
