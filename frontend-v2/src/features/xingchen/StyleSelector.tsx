import type { XcStyle } from './intent'

const OPTIONS: { value: XcStyle; icon: string; label: string }[] = [
  { value: 'quick', icon: '⚡', label: '快速问答' },
  { value: 'report', icon: '📋', label: '深度研报' },
  { value: 'debate', icon: '⚔️', label: '多空辩论' },
  { value: 'teach', icon: '🎓', label: '教学解释' },
]

/** 回应方式选择器（⚡快速 / 📋研报 / ⚔️辩论 / 🎓教学）→ 下发 style。 */
export function StyleSelector({
  value,
  onChange,
}: {
  value: XcStyle
  onChange: (s: XcStyle) => void
}) {
  return (
    <div role="radiogroup" aria-label="回应方式" className="flex flex-wrap gap-1.5">
      {OPTIONS.map((o) => {
        const active = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={
              'rounded-tile border px-2.5 py-1 text-label transition-colors ' +
              (active
                ? 'border-brand-1 bg-brand-1 text-white'
                : 'border-sf-line bg-sf-surface-2 text-sf-ink-2 hover:border-sf-accent')
            }
          >
            <span aria-hidden="true" className="mr-1">
              {o.icon}
            </span>
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
