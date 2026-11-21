import { useEffect, useId, useState } from 'react'
import { useStockSearch } from '@/lib/queries'
import {
  STOCK_MATCH_LABEL,
  stockMatchKind,
  type StockSearchItem,
} from '@/api/schemas/stockSearch'

/** 轻量防抖：输入框连续打字时只在停手 200ms 后发一次请求。 */
function useDebounced<T>(value: T, ms = 200): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export interface StockSearchInputProps {
  /** 外部当前代码（选中后父级回写，输入框同步显示） */
  value?: string
  /** 选中某只股票；item 为 null 表示「按 6 位代码直接查询」，未编造名称 */
  onSelect: (code: string, item: StockSearchItem | null) => void
  label?: string
  placeholder?: string
  limit?: number
  /** 允许无匹配时回车直接按 6 位代码查询（默认 true） */
  allowRawCode?: boolean
  /** 可选：输入文本变化即回传父级（写表单需拿原始输入，不等到选中候选） */
  onTextChange?: (text: string) => void
  className?: string
}

/**
 * v2 股票搜索输入（对齐 v1 `search_ui.stock_search_input` 的能力，但零 Streamlit）：
 *  - 代码 / 名称 / 拼音首字母 / 拼音全拼四种召回，走真实后端 `/api/stocks/search`；
 *  - 「匹配结果」下拉列出候选，显示名称、代码、市场与匹配方式标签；
 *  - 键盘 ↑↓ 选择 / Enter 确认 / Esc 关闭；
 *  - 空结果、请求失败、加载中三态分明，绝不把失败洗成「无匹配」；
 *  - 不合成假股票：无匹配时可回车按原始 6 位代码查询，名称留空由数据层决定。
 */
export function StockSearchInput({
  value = '',
  onSelect,
  label = '搜索股票',
  placeholder = '代码 / 名称 / 拼音首字母，如 600519、茅台、gzmt',
  limit = 10,
  allowRawCode = true,
  onTextChange,
  className = '',
}: StockSearchInputProps) {
  const [text, setText] = useState(value)
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const listId = useId()
  useEffect(() => setText(value), [value])

  const trimmed = text.trim()
  const debounced = useDebounced(trimmed)
  const q = useStockSearch(debounced, limit)
  const results = q.data ?? []
  // 防抖窗口内先给「搜索中…」，避免下拉出现约 200ms 的纯空白（真实交互缺陷）。
  const pending = trimmed.length > 0 && (trimmed !== debounced || q.isFetching)
  const rawCode = allowRawCode && /^\d{6}$/.test(trimmed)

  function pick(item: StockSearchItem) {
    setText(item.code)
    setOpen(false)
    setCursor(0)
    onSelect(item.code, item)
  }

  function pickRaw() {
    const code = text.trim()
    setOpen(false)
    onSelect(code, null)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setCursor((c) => Math.min(results.length - 1, c + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(0, c - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (results[cursor]) pick(results[cursor])
      else if (rawCode) pickRaw()
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div
      className={`relative ${className}`}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false)
      }}
    >
      {label && (
        <label className="mb-1 block text-label text-sf-ink-3" htmlFor={`${listId}-input`}>
          {label}
        </label>
      )}
      <input
        id={`${listId}-input`}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value)
          onTextChange?.(e.target.value)
          setOpen(true)
          setCursor(0)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className="w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
      />

      {open && (
        <div
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-tile border border-sf-line bg-sf-surface p-1 shadow-lg"
        >
          {pending && (
            <p className="px-2 py-1.5 text-label text-sf-ink-3">搜索中…</p>
          )}
          {!pending && q.isError && (
            <p role="alert" className="px-2 py-1.5 text-label text-sf-danger">
              搜索失败：{q.error instanceof Error ? q.error.message : '原因不可得'}
            </p>
          )}
          {!pending && !q.isError && results.length === 0 && debounced && (
            <div className="px-2 py-1.5 text-label text-sf-ink-3">
              <p>未找到匹配的股票</p>
              <p className="mt-0.5">可试试代码、中文名或拼音首字母（如 gzmt）</p>
            </div>
          )}
          {results.map((item, i) => {
            const kind = stockMatchKind(debounced || trimmed, item)
            return (
              <button
                key={item.code}
                type="button"
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onClick={() => pick(item)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-body hover:bg-sf-surface-2 ${
                  i === cursor ? 'bg-sf-surface-2 text-sf-ink' : 'text-sf-ink-2'
                }`}
              >
                <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
                <span className="font-mono text-label text-sf-ink-3">{item.code}</span>
                <span className="rounded border border-sf-line px-1 text-[11px] text-sf-ink-3">
                  {item.market ?? '—'}
                </span>
                <span className="rounded bg-sf-surface-2 px-1 text-[11px] text-sf-accent">
                  {STOCK_MATCH_LABEL[kind]}
                </span>
              </button>
            )
          })}
          {rawCode && (
            <button
              type="button"
              onClick={pickRaw}
              className="mt-1 w-full rounded border-t border-sf-line px-2 py-1.5 text-left text-label text-sf-ink-2 hover:text-sf-accent"
            >
              直接按代码 {text.trim()} 查询（未匹配到名称，不臆造股票信息）
            </button>
          )}
        </div>
      )}
    </div>
  )
}
