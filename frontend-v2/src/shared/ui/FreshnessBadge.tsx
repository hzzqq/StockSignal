import type { FreshnessLevel } from '@/lib/freshness'
import { freshnessLabel } from '@/lib/freshness'

const STYLES: Record<FreshnessLevel, string> = {
  ok: 'bg-ss-up/15 text-ss-up border-ss-up/30',
  warn: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  stale: 'bg-ss-down/15 text-ss-down border-ss-down/30',
  unknown: 'bg-sf-border text-sf-txt/70 border-sf-border',
}

/** 新鲜度徽标（仅可视化，不携带任何仓位计算逻辑）。 */
export function FreshnessBadge({ level }: { level: FreshnessLevel }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs ${STYLES[level]}`}
    >
      {freshnessLabel(level)}
    </span>
  )
}
