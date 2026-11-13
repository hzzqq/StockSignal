/**
 * 缺参追问卡片（= FinPilot param-prompt）：意图分类判定缺分析标的时向用户追问。
 * 可点击条目回填 Composer（onPick），不强迫。
 */
export function ParamPromptCard({
  prompts,
  onPick,
}: {
  prompts: string[]
  onPick?: (p: string) => void
}) {
  if (!prompts.length) return null
  return (
    <div className="rounded-tile border border-sf-warn bg-sf-warn-soft px-3 py-2">
      <div className="flex items-center gap-1.5 text-label text-sf-warn">
        <span aria-hidden="true">⚠️</span>
        <span>需要补充一点信息</span>
      </div>
      <ul className="mt-2 space-y-1.5">
        {prompts.map((p, i) => (
          <li key={i}>
            {onPick ? (
              <button
                type="button"
                onClick={() => onPick(p)}
                className="text-left text-body text-sf-ink-2 hover:text-sf-accent"
              >
                · {p}
              </button>
            ) : (
              <span className="text-body text-sf-ink-2">· {p}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
