// 图表配色令牌（与 src/styles/tokens.css 的 --color-sf-* / --color-ss-* 严格对齐）。
// ECharts 是 canvas，吃不到 Tailwind class，故在此集中维护 hex 常量。
export const CHART = {
  // A股交易屏语义：涨=红、跌=绿
  up: '#ff4d4f',
  down: '#00d486',
  // 报告/个股页语义（绿涨红跌），预留
  docUp: '#009e60',
  docDown: '#ff4d4f',
  // 暗色背景体系
  bg: '#0f0f23',
  card: '#1a1a2e',
  txt: '#e2e8f0',
  border: '#2d2d44',
  grid: '#23233c',
} as const
