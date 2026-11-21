import { useId, useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { NAV, type AppPath } from '@/nav/nav'

interface FeatureHit {
  to: AppPath
  label: string
  group: string
  icon: string
}

/** 唯一数据源：NAV（侧栏分类的真源）。不另抄路径表，新增功能自动可被搜到。 */
const ALL_FEATURES: FeatureHit[] = NAV.flatMap((g) =>
  g.items.map((it) => ({ to: it.to, label: it.label, icon: it.icon, group: g.group })),
)

/**
 * 顶栏轻量「功能搜索」（命令面板的最小形态）。
 *  - 关键字同时匹配功能名与分组名，大小写不敏感；
 *  - ↑↓ 选择 / Enter 用 useNavigate 跳到 NAV 里的 to / Esc 或失焦关闭；
 *  - 空结果给中文提示，不自造功能、不硬编码路由。
 */
export function FeatureSearch() {
  const navigate = useNavigate()
  const listId = useId()
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)

  const q = text.trim().toLocaleLowerCase()
  const hits = useMemo(() => {
    if (!q) return []
    return ALL_FEATURES.filter(
      (f) =>
        f.label.toLocaleLowerCase().includes(q) || f.group.toLocaleLowerCase().includes(q),
    ).slice(0, 8)
  }, [q])

  function select(hit: FeatureHit) {
    setText('')
    setOpen(false)
    setCursor(0)
    void navigate({ to: hit.to })
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      if (!q) return
      e.preventDefault()
      setOpen(true)
      setCursor((c) => Math.min(hits.length - 1, c + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(0, c - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const hit = hits[cursor]
      if (hit) select(hit)
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div
      className="relative hidden w-40 md:block lg:w-48"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false)
      }}
    >
      <input
        type="text"
        role="combobox"
        aria-label="功能搜索"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        value={text}
        placeholder="搜索功能…"
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
          setCursor(0)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className="w-full rounded-tile border border-sf-line bg-sf-surface px-2 py-1 text-label text-sf-ink outline-none focus:border-sf-accent"
      />
      {open && q && (
        <div
          id={listId}
          role="listbox"
          className="absolute right-0 z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-tile border border-sf-line bg-sf-surface p-1 shadow-lg"
        >
          {hits.length === 0 ? (
            <p role="status" className="px-2 py-1.5 text-label text-sf-ink-3">
              未找到匹配的功能，换个关键词试试
            </p>
          ) : (
            hits.map((hit, i) => (
              <button
                key={hit.to}
                type="button"
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onClick={() => select(hit)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-label hover:bg-sf-surface-2 ${
                  i === cursor ? 'bg-sf-surface-2 text-sf-ink' : 'text-sf-ink-2'
                }`}
              >
                <span aria-hidden="true" className="w-4 shrink-0 text-center text-sf-ink-3">
                  {hit.icon}
                </span>
                <span className="min-w-0 flex-1 truncate">{hit.label}</span>
                <span className="shrink-0 text-sf-ink-3">{hit.group}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
