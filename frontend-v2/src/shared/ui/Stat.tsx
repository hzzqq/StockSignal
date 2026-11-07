import type { ReactNode } from 'react'

/**
 * 轻量卡片流 · 单指标卡：标签 + 大数值 + 可选副文。
 * 数值用等宽数字（tabular-nums）避免抖动；color 用于 A 股涨跌语义着色（调用方传 hex）。
 * 层级：标签 L3 / 数值 L1 / 副文 L3，实色令牌，不再用 /40 这类透明度混合。
 */
export function Stat({
  label,
  value,
  sub,
  color,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  color?: string
}) {
  return (
    <div className="rounded-tile bg-sf-surface-2 border border-sf-line px-3.5 py-3">
      <div className="text-label text-sf-ink-3">{label}</div>
      <div
        className="text-kpi font-semibold leading-tight mt-0.5 tabular-nums"
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {sub != null && <div className="text-label text-sf-ink-3 mt-1">{sub}</div>}
    </div>
  )
}
