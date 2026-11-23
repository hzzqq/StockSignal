/** 页面级双 tab 切换条（2026-11-22 侧栏减臃肿：相似页并入同一路由的 tab 视图）。
 *
 *  语义约定（与 LoginPage 的 tablist 一致）：
 *   - role=tablist/tab + aria-selected，键盘 button 天然可聚焦；
 *   - 选中态品牌渐变底，未选中态弱化 ink-2；
 *   - 持久化由调用方负责（本组件只受控渲染）。
 */
export interface PageTab {
  key: string
  label: string
}

export function PageTabs({
  tabs,
  active,
  onChange,
  ariaLabel,
  wide = false,
}: {
  tabs: readonly PageTab[]
  active: string
  onChange: (key: string) => void
  ariaLabel: string
  wide?: boolean
}) {
  return (
    <div
      className={`flex rounded-tile border border-sf-line bg-sf-surface-2 p-1 mb-4 ${wide ? 'max-w-[720px]' : 'max-w-[420px]'}`}
      role="tablist"
      aria-label={ariaLabel}
    >
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={`flex-1 py-1.5 rounded-tile border-0 cursor-pointer text-label font-semibold ${
            active === t.key ? 'text-white' : 'text-sf-ink-2 bg-transparent hover:text-sf-ink'
          }`}
          style={
            active === t.key
              ? { background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))' }
              : undefined
          }
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
