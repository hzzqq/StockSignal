/** assistant 轮末尾的可点击追问 chips（点击直接发送）。 */
export function SuggestionChips({
  chips,
  onPick,
}: {
  chips: string[]
  onPick?: (c: string) => void
}) {
  if (!chips.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {chips.map((c, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onPick?.(c)}
          className="rounded-tile border border-sf-line bg-sf-surface-2 px-2.5 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
        >
          {c}
        </button>
      ))}
    </div>
  )
}
