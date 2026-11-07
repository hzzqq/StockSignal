// 图表配色令牌（与 src/styles/tokens.css 的 --color-* 严格对齐，DESIGN.md §2）。
// ECharts 是 canvas，吃不到 Tailwind class，故在此集中维护 hex 常量。
// 轻量卡片流：轴线/网格走低对比 hairline，正文走 L3 弱文，只有涨跌系列才用高饱和色。
export const CHART = {
  // A股交易屏语义：涨=红、跌=绿（仅用于价格/涨跌系列）
  up: '#ff4d4f',
  down: '#00d486',
  // 报告/个股页语义（绿涨红跌），预留
  docUp: '#009e60',
  docDown: '#ff4d4f',

  // 暗色背景体系（W0 旧值，保留兼容）
  bg: '#0f0f23',
  card: '#1a1a2e',
  txt: '#e2e8f0',
  border: '#2d2d44',
  grid: '#23233c',

  // 轻量卡片流 · 语义表面/文字（与 tokens.css 逐项对齐）
  surface: '#16162c',
  surface2: '#1d1d38',
  line: '#26263f',
  ink2: '#a8b2cc',
  ink3: '#7c86a3',
  warn: '#e5a54b',
  danger: '#e06c75',
  ok: '#5bb98c',
  accent: '#9aa6e8',
} as const

// 亮色主题图表配色（与 tokens.css html[data-theme="light"] 逐项对齐）。
// docUp 写死与 color-mix 等价的字面 hex，避免运行时计算 color-mix 产生 1/255 舍入差。
export const CHART_LIGHT = {
  up: '#bf3a3b', down: '#00754a', docUp: '#007648', docDown: '#bf3a3b',
  bg: '#f0f3f9', card: '#ffffff', txt: '#20284a', border: '#dbe0ec', grid: '#e8ecf4',
  surface: '#ffffff', surface2: '#f6f8fd', line: '#dbe0ec',
  ink2: '#414c6b', ink3: '#5f6a87',
  warn: '#8a5300', danger: '#b02a3a', ok: '#376f54', accent: '#4657c8',
} as const

export type ChartTheme = 'dark' | 'light'

/** Readonly<typeof CHART> 的兼容写法：键锚定 CHART，值宽化为 string，
 *  使 CHART_LIGHT 也能直接返回，无需破坏 as const 的强转。 */
export type ChartPalette = Readonly<{ [K in keyof typeof CHART]: string }>

/** 按主题取图表配色：dark 返回既有 CHART，light 返回 CHART_LIGHT。 */
export function chartPalette(theme: ChartTheme): ChartPalette {
  return theme === 'dark' ? CHART : CHART_LIGHT
}

// 暗色 hex → 亮色 hex 查表。CHART.up 与 CHART.docDown 同为 #ff4d4f、CHART_LIGHT 中
// 两者也同为 #bf3a3b，重复键映射一致，不产生歧义。
const DARK_TO_LIGHT: ReadonlyMap<string, string> = new Map<string, string>(
  (Object.keys(CHART) as (keyof typeof CHART)[]).map(
    (key): [string, string] => [CHART[key], CHART_LIGHT[key]],
  ),
)

/**
 * 递归把 ECharts option 中「值等于 CHART 任一 hex」的字符串替换为 CHART_LIGHT 对应值，
 * 其余（含 formatter 函数、Date 等非普通对象）原样保留；dark 主题原样返回。
 */
export function remapChartColors(option: unknown, theme: ChartTheme): unknown {
  if (theme === 'dark') return option
  const walk = (value: unknown): unknown => {
    if (typeof value === 'string') return DARK_TO_LIGHT.get(value) ?? value
    if (Array.isArray(value)) return value.map(walk)
    if (value !== null && typeof value === 'object') {
      const proto = Object.getPrototypeOf(value)
      if (proto === Object.prototype || proto === null) {
        return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, walk(v)]))
      }
    }
    return value
  }
  return walk(option)
}
