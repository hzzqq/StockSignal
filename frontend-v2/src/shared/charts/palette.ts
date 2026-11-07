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
