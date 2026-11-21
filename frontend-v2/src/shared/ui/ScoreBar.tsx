/**
 * 通用「评分进度条」：维度分（0-100）映射为横向填充条。
 *
 * - value=null（或 NaN/Infinity）：右侧显示「—」，填充条不渲染、无 aria-valuenow，
 *   绝不补 0/50（诚实缺失，对齐项目「缺失不画条」约定）。
 * - value 为数字：clamp 到 [0,100]，宽度 = `${pct}%`，填充条带 meter 语义
 *   （role/aria-valuenow/aria-valuemin/aria-valuemax/aria-label）。
 * - 配色：默认用 CSS 令牌 var(--color-sf-accent)（评分不是涨跌，不借用红涨绿跌的
 *   价格域语义）；调用方可用 color 覆盖。
 */
export interface ScoreBarProps {
  label: string
  value: number | null
  color?: string
  className?: string
}

export function ScoreBar({ label, value, color, className = '' }: ScoreBarProps) {
  const hasValue = value != null && Number.isFinite(value)
  const pct = hasValue ? Math.min(100, Math.max(0, value as number)) : 0

  return (
    <div className={`text-sf-ink ${className}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-label text-sf-ink-2">{label}</span>
        <span className={`tabular-nums ${hasValue ? 'text-body text-sf-ink' : 'text-body text-sf-ink-3'}`}>
          {hasValue ? pct : '—'}
        </span>
      </div>
      {hasValue && (
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sf-line/50">
          <div
            role="meter"
            aria-label={label}
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-full rounded-full"
            style={{ width: `${pct}%`, backgroundColor: color ?? 'var(--color-sf-accent)' }}
          />
        </div>
      )}
    </div>
  )
}
