import { useTheme } from '@/app/providers'
import type { ThemePref } from '@/lib/theme'

/** 三态主题切换：radiogroup + 原生 button（键盘可达），选中态只用 hairline 强调边框，不借涨跌色。 */
const OPTIONS: { value: ThemePref; label: string }[] = [
  { value: 'dark', label: '深色' },
  { value: 'light', label: '浅色' },
  { value: 'system', label: '跟随系统' },
]

export function ThemeToggle() {
  const { pref, setPref } = useTheme()
  return (
    <div role="radiogroup" aria-label="主题" className="flex items-center gap-1">
      {OPTIONS.map((o) => {
        const active = pref === o.value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setPref(o.value)}
            className={[
              'px-2 py-1 rounded-tile text-label bg-sf-surface-2 border transition-colors',
              active ? 'text-sf-ink border-sf-line-strong' : 'text-sf-ink-2 border-sf-line',
            ].join(' ')}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
