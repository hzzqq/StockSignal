import type { ReactNode } from 'react'

/** 单指标卡：标签 + 大数值 + 可选副文。color 用于 A 股涨跌语义着色（由调用方传 hex）。 */
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
    <div className="rounded-lg bg-sf-bg/40 border border-sf-border p-3">
      <div className="text-xs text-sf-txt/60">{label}</div>
      <div className="text-xl font-semibold leading-tight mt-0.5" style={color ? { color } : undefined}>
        {value}
      </div>
      {sub != null && <div className="text-xs text-sf-txt/50 mt-1">{sub}</div>}
    </div>
  )
}
