import type { FreshnessLevel } from '@/lib/freshness'
import { freshnessLabel } from '@/lib/freshness'

/**
 * 轻量卡片流 · 数据新鲜度徽标（仅可视化，不携带任何仓位计算逻辑）。
 *
 * 语义纠偏（DESIGN.md §2.1）：历史实现把交易屏涨色(红) 当「新鲜」、跌色(绿)
 * 当「陈旧」，方向与 A 股价格语义恰好拧反，且状态不该复用价格色。现改用专用
 * 状态色 sf-ok / sf-warn / sf-danger，细边框 + 低饱和底，克制不抢视觉。
 * 颜色之外另带形状点（●/▲/■ 由 aria 文案补足），不依赖单一色彩通道传达信息。
 */
const STYLES: Record<FreshnessLevel, string> = {
  ok: 'bg-sf-ok/10 text-sf-ok border-sf-ok/30',
  warn: 'bg-sf-warn/10 text-sf-warn border-sf-warn/30',
  stale: 'bg-sf-danger/10 text-sf-danger border-sf-danger/30',
  unknown: 'bg-sf-surface-2 text-sf-ink-3 border-sf-line',
}

export function FreshnessBadge({ level }: { level: FreshnessLevel }) {
  return (
    <span
      role="status"
      aria-label={`数据新鲜度：${freshnessLabel(level)}`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-tile border text-label ${STYLES[level]}`}
    >
      <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-current" />
      {freshnessLabel(level)}
    </span>
  )
}
