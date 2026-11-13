import { useState } from 'react'

/**
 * 问题分析卡（= FinPilot 中间过程折叠卡）。
 * 数据源：intent.ts 的规则引擎步骤（planner→analysis→debate），零 LLM 成本。
 */
export function ProcessCard({
  steps,
  title = '🧠 问题分析（规则引擎）',
  confidence,
  defaultOpen = false,
}: {
  steps: string[]
  title?: string
  confidence?: number
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between text-label text-sf-ink-3"
      >
        <span>
          {title}
          {typeof confidence === 'number' && (
            <span className="ml-1 text-sf-ink-3/80">· 置信 {(confidence * 100).toFixed(0)}%</span>
          )}
        </span>
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <ol className="mt-2 space-y-1 border-l border-sf-line pl-3 text-label text-sf-ink-2">
          {steps.map((s, i) => (
            <li key={i} className="relative">
              <span
                aria-hidden="true"
                className="absolute -left-[1.05rem] top-1.5 h-1.5 w-1.5 rounded-full bg-sf-accent"
              />
              {s}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
