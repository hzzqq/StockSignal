import { useState, type FormEvent } from 'react'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import {
  useAddJunkStock,
  useAddWatchlist,
  useAddWatchlistBatch,
  useDeleteJunkStock,
  useDeleteJunkStockBatch,
  useDeleteUserScore,
  useDeleteWatchlist,
  useDeleteWatchlistBatch,
  useJunkStocksQuery,
  useUserScoresQuery,
  useUpsertUserScore,
  useWatchlistQuery,
} from '@/lib/queriesUserCollections'

/**
 * 用户三组写能力面板（v1 自选股 / 垃圾股 / 自定义打分 → v2 对齐批次）。
 *
 * 后端早已有 /api/watchlist、/api/junk-stocks、/api/user-scores 全套写端点，
 * 但 v2 此前只有只读盯盘页，写能力整批悬空。本组件只做接线：
 *  - 读：use*Query（服务端是真源）；
 *  - 写：全部经 lib/queriesUserCollections.ts 的统一 mutation 工厂，成功后失效重取；
 *  - 诚实：重复添加返回 data=null 时如实显示「已在…中」，不冒充新增成功；
 *  - 错误：原样展示后端 message，不吞错、不把 error 洗成成功；
 *  - 空值：null 显示「—」，不 `?? 0` / `|| 0` / `new Date()` 兜底。
 *
 * ⚠️ 本文件不含任何实盘交易能力。
 */

const inputCls =
  'mt-1 w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent'
const labelCls = 'block text-label text-sf-ink-3'

function firstError(errors: unknown[]): string | null {
  for (const e of errors) {
    if (e instanceof Error) return e.message
  }
  return null
}

/** 不用 role="alert"：同页只读区已有 role=alert 守卫，避免抢唯一性；文案本身已明确是「操作失败」。 */
function Hint({ text, isError }: { text: string; isError: boolean }) {
  return (
    <p
      className={
        isError
          ? 'my-2 rounded-tile border border-sf-danger bg-sf-surface px-3 py-2 text-label text-sf-danger'
          : 'my-2 rounded-tile border border-sf-line bg-sf-surface px-3 py-2 text-label text-sf-ink-2'
      }
    >
      {isError ? `操作失败：${text}` : text}
    </p>
  )
}

/** 逗号 / 空白分隔的文本 → 非空字符串数组（不去重，由后端决定跳过策略）。 */
function splitCodes(raw: string): string[] {
  return raw
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

/** 逗号 / 空白分隔的文本 → 整数 id 数组；含非整数时返回 null，交调用方如实报错。 */
function splitIds(raw: string): number[] | null {
  const parts = raw
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
  if (parts.length === 0) return null
  const ids: number[] = []
  for (const p of parts) {
    if (!/^\d+$/.test(p)) return null
    ids.push(Number(p))
  }
  return ids
}

/**
 * 单行危险操作就地二次确认（与批量删除 confirmingBatchDelete 同范式）：
 * 首击不改数据，只切到确认态；确认按钮才执行、在途禁用；取消复位。
 * aria-label 由调用方原样传入，保留原可访问名。
 */
function InlineDeleteConfirm({
  label,
  pending,
  confirming,
  onRequest,
  onConfirm,
  onCancel,
}: {
  label: string
  pending: boolean
  confirming: boolean
  onRequest: () => void
  onConfirm: () => void
  onCancel: () => void
}) {
  if (confirming) {
    return (
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-label text-sf-ink-2">确认删除 {label}？</span>
        <Button type="button" variant="danger" size="sm" disabled={pending} onClick={onConfirm}>
          {pending ? '删除中…' : '确认删除'}
        </Button>
        <Button type="button" variant="ghost" size="sm" disabled={pending} onClick={onCancel}>
          取消
        </Button>
      </span>
    )
  }
  return (
    <Button
      type="button"
      variant="danger"
      size="sm"
      aria-label={`删除${label}`}
      disabled={pending}
      onClick={onRequest}
    >
      {pending ? '删除中…' : '删除'}
    </Button>
  )
}

function WatchlistPanel() {
  const q = useWatchlistQuery()
  const add = useAddWatchlist()
  const del = useDeleteWatchlist()
  const addBatch = useAddWatchlistBatch()
  const delBatch = useDeleteWatchlistBatch()
  const [code, setCode] = useState('')
  // 选中项名称（来自搜索结果 item），仅用于回显；POST /watchlist 契约只收 {stock_code, note}，
  // 名称由后端读端点水合，前端不臆造、不额外写库。
  const [selName, setSelName] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [batchText, setBatchText] = useState('')
  const [idText, setIdText] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // 危险操作就地二次确认：批量删除按填写的 id 删除，首击只置确认态，不改数据。
  const [confirmingBatchDelete, setConfirmingBatchDelete] = useState(false)
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null)

  function resetMessages() {
    setLocalError(null)
    setNotice(null)
    add.reset()
    addBatch.reset()
    del.reset()
    delBatch.reset()
  }

  function handleAdd(e: FormEvent) {
    e.preventDefault()
    resetMessages()
    const stockCode = code.trim()
    if (!stockCode) {
      setLocalError('股票代码不能为空')
      return
    }
    add.mutate(
      { stock_code: stockCode, note: note.trim().length > 0 ? note.trim() : undefined },
      {
        onSuccess: (data) => {
          setNotice(data === null ? '已在自选股中' : `已加入自选股：${data.stock_code}`)
          setCode('')
          setSelName(null)
          setNote('')
        },
      },
    )
  }

  function handleBatchAdd() {
    resetMessages()
    const codes = splitCodes(batchText)
    if (codes.length === 0) {
      setLocalError('批量代码不能为空')
      return
    }
    addBatch.mutate({ codes }, {
      onSuccess: (data) => {
        setNotice(`新增 ${data.added.length} 只，跳过 ${data.skipped.length} 只，失败 ${data.failed.length} 只`)
        setBatchText('')
      },
    })
  }

  function handleBatchDelete() {
    resetMessages()
    const ids = splitIds(idText)
    if (ids === null || ids.length === 0) {
      setLocalError('请填写要删除的数字 id（逗号分隔）')
      return
    }
    delBatch.mutate({ ids }, {
      onSuccess: (data) => {
        setNotice(`已删除 ${data.deleted.length} 只，无权 ${data.forbidden.length} 只，不存在 ${data.not_found.length} 只`)
        setIdText('')
        setConfirmingBatchDelete(false)
      },
    })
  }

  const err = localError ?? firstError([add.error, del.error, addBatch.error, delBatch.error])

  return (
    <Card title="自选股（可写 · 按登录用户隔离）">
      <div className="space-y-4">
        <form onSubmit={handleAdd} className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <StockSearchInput
              value={code}
              label="添加自选股"
              onSelect={(nextCode, item) => {
                setCode(nextCode)
                setSelName(item?.name ?? null)
              }}
            />
            <label className={labelCls}>
              备注（可选）
              <input value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} />
            </label>
          </div>
          {code.trim() !== '' && (
            <p className="text-label text-sf-ink-3">
              {`已选：${selName ?? code.trim()}（${code.trim()}）`}
            </p>
          )}
          <Button type="submit" variant="primary" size="sm" disabled={add.isPending}>
            {add.isPending ? '添加中…' : '加入自选股'}
          </Button>
        </form>

        <div className="space-y-2 rounded-tile border border-sf-line p-3">
          <label className={labelCls}>
            批量添加（代码，逗号分隔）
            <input value={batchText} onChange={(e) => setBatchText(e.target.value)} className={inputCls} />
          </label>
          <Button type="button" variant="secondary" size="sm" onClick={handleBatchAdd} disabled={addBatch.isPending}>
            {addBatch.isPending ? '批量添加中…' : '批量添加'}
          </Button>
          <label className={labelCls}>
            批量删除（列表中的数字 id，逗号分隔）
            <input value={idText} onChange={(e) => setIdText(e.target.value)} className={inputCls} />
          </label>
          {confirmingBatchDelete ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-label text-sf-ink-2">确认批量删除？将删除填写的全部 id</span>
              <Button type="button" variant="danger" size="sm" disabled={delBatch.isPending} onClick={handleBatchDelete}>
                {delBatch.isPending ? '批量删除中…' : '确认批量删除'}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmingBatchDelete(false)}>
                取消
              </Button>
            </div>
          ) : (
            <Button type="button" variant="secondary" size="sm" onClick={() => setConfirmingBatchDelete(true)} disabled={delBatch.isPending}>
              {delBatch.isPending ? '批量删除中…' : '批量删除'}
            </Button>
          )}
        </div>

        {err && <Hint text={err} isError />}
        {notice && !err && <Hint text={notice} isError={false} />}

        <QueryState
          isLoading={q.isLoading}
          isError={q.isError}
          error={q.error}
          isEmpty={q.data !== undefined && q.data.length === 0}
          emptyLabel="暂无自选股"
          emptyHint="在上方选股并加入后，会出现在这里"
        >
          <ul className="space-y-1">
            {q.data?.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-x-3 text-body">
                <span className="font-medium text-sf-ink">{item.stock_code}</span>
                {item.stock_name && <span className="text-sf-ink-2">{item.stock_name}</span>}
                {item.note && <span className="text-label text-sf-ink-3">{item.note}</span>}
                <span className="text-label text-sf-ink-3">id={item.id}</span>
                <InlineDeleteConfirm
                  label={`自选股 ${item.stock_code}`}
                  pending={del.isPending}
                  confirming={confirmingDeleteId === item.id}
                  onRequest={() => { resetMessages(); setConfirmingDeleteId(item.id) }}
                  onCancel={() => setConfirmingDeleteId(null)}
                  onConfirm={() => {
                    del.mutate({ id: item.id }, {
                      onSuccess: () => { setNotice(`已删除 ${item.stock_code}`); setConfirmingDeleteId(null) },
                    })
                  }}
                />
              </li>
            ))}
          </ul>
        </QueryState>
      </div>
    </Card>
  )
}

function JunkStockPanel() {
  const q = useJunkStocksQuery()
  const add = useAddJunkStock()
  const del = useDeleteJunkStock()
  const delBatch = useDeleteJunkStockBatch()
  const [code, setCode] = useState('')
  // 选中项名称（来自搜索结果 item），仅用于回显；POST /junk-stocks 契约只收 {stock_code, note}，
  // 名称由后端读端点水合，前端不臆造、不额外写库。
  const [selName, setSelName] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [idText, setIdText] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // 危险操作就地二次确认：批量删除按填写的 id 删除，首击只置确认态，不改数据。
  const [confirmingBatchDelete, setConfirmingBatchDelete] = useState(false)
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null)

  function resetMessages() {
    setLocalError(null)
    setNotice(null)
    add.reset()
    del.reset()
    delBatch.reset()
  }

  function handleAdd(e: FormEvent) {
    e.preventDefault()
    resetMessages()
    const stockCode = code.trim()
    if (!stockCode) {
      setLocalError('股票代码不能为空')
      return
    }
    add.mutate(
      { stock_code: stockCode, note: note.trim().length > 0 ? note.trim() : undefined },
      {
        onSuccess: (data) => {
          setNotice(data === null ? '已在垃圾股中' : `已加入垃圾股：${data.stock_code}`)
          setCode('')
          setSelName(null)
          setNote('')
        },
      },
    )
  }

  function handleBatchDelete() {
    resetMessages()
    const ids = splitIds(idText)
    if (ids === null || ids.length === 0) {
      setLocalError('请填写要删除的数字 id（逗号分隔）')
      return
    }
    delBatch.mutate({ ids }, {
      onSuccess: (data) => {
        setNotice(`已删除 ${data.deleted.length} 只`)
        setIdText('')
        setConfirmingBatchDelete(false)
      },
    })
  }

  const err = localError ?? firstError([add.error, del.error, delBatch.error])

  return (
    <Card title="垃圾股回避池（可写 · 按登录用户隔离）">
      <div className="space-y-4">
        <form onSubmit={handleAdd} className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <StockSearchInput
              value={code}
              label="加入回避池"
              onSelect={(nextCode, item) => {
                setCode(nextCode)
                setSelName(item?.name ?? null)
              }}
            />
            <label className={labelCls}>
              备注（可选）
              <input value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} />
            </label>
          </div>
          {code.trim() !== '' && (
            <p className="text-label text-sf-ink-3">
              {`已选：${selName ?? code.trim()}（${code.trim()}）`}
            </p>
          )}
          <Button type="submit" variant="primary" size="sm" disabled={add.isPending}>
            {add.isPending ? '添加中…' : '加入回避池'}
          </Button>
        </form>

        <div className="space-y-2 rounded-tile border border-sf-line p-3">
          <label className={labelCls}>
            批量删除（数字 id，逗号分隔）
            <input value={idText} onChange={(e) => setIdText(e.target.value)} className={inputCls} />
          </label>
          {confirmingBatchDelete ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-label text-sf-ink-2">确认批量删除？将删除填写的全部 id</span>
              <Button type="button" variant="danger" size="sm" disabled={delBatch.isPending} onClick={handleBatchDelete}>
                {delBatch.isPending ? '批量删除中…' : '确认批量删除'}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmingBatchDelete(false)}>
                取消
              </Button>
            </div>
          ) : (
            <Button type="button" variant="secondary" size="sm" onClick={() => setConfirmingBatchDelete(true)} disabled={delBatch.isPending}>
              {delBatch.isPending ? '批量删除中…' : '批量删除'}
            </Button>
          )}
        </div>

        {err && <Hint text={err} isError />}
        {notice && !err && <Hint text={notice} isError={false} />}

        <QueryState
          isLoading={q.isLoading}
          isError={q.isError}
          error={q.error}
          isEmpty={q.data !== undefined && q.data.length === 0}
          emptyLabel="暂无垃圾股标记"
          emptyHint="在上方选股并加入后，会出现在这里"
        >
          <ul className="space-y-1">
            {q.data?.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-x-3 text-body">
                <span className="font-medium text-sf-ink">{item.stock_code}</span>
                {item.stock_name && <span className="text-sf-ink-2">{item.stock_name}</span>}
                {item.note && <span className="text-label text-sf-ink-3">{item.note}</span>}
                <InlineDeleteConfirm
                  label={`垃圾股 ${item.stock_code}`}
                  pending={del.isPending}
                  confirming={confirmingDeleteId === item.id}
                  onRequest={() => { resetMessages(); setConfirmingDeleteId(item.id) }}
                  onCancel={() => setConfirmingDeleteId(null)}
                  onConfirm={() => {
                    del.mutate({ id: item.id }, {
                      onSuccess: () => { setNotice(`已删除 ${item.stock_code}`); setConfirmingDeleteId(null) },
                    })
                  }}
                />
              </li>
            ))}
          </ul>
        </QueryState>
      </div>
    </Card>
  )
}

function UserScorePanel() {
  const q = useUserScoresQuery()
  const upsert = useUpsertUserScore()
  const del = useDeleteUserScore()
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [scoreText, setScoreText] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [confirmingDeleteCode, setConfirmingDeleteCode] = useState<string | null>(null)

  function resetMessages() {
    setLocalError(null)
    setNotice(null)
    upsert.reset()
    del.reset()
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    resetMessages()
    const stockCode = code.trim()
    if (!stockCode) {
      setLocalError('股票代码不能为空')
      return
    }
    const score = Number(scoreText)
    if (!Number.isInteger(score) || score < 0 || score > 100) {
      setLocalError('分数须在 0–100 之间')
      return
    }
    upsert.mutate(
      {
        stock_code: stockCode,
        stock_name: name.trim().length > 0 ? name.trim() : undefined,
        score,
      },
      {
        onSuccess: (data) => {
          setNotice(`已保存 ${data.stock_code}：${data.score} 分`)
          setScoreText('')
        },
      },
    )
  }

  const err = localError ?? firstError([upsert.error, del.error])

  return (
    <Card title="我的自定义打分（可写 · 0–100）">
      <div className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-3">
            <StockSearchInput
              value={code}
              label="打分股票"
              onSelect={(nextCode, item) => {
                setCode(nextCode)
                if (item) setName(item.name)
              }}
            />
            <label className={labelCls}>
              名称（可选）
              <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
            </label>
            <label className={labelCls}>
              分数（0–100 整数）
              <input
                type="number"
                value={scoreText}
                onChange={(e) => setScoreText(e.target.value)}
                className={inputCls}
              />
            </label>
          </div>
          <Button type="submit" variant="primary" size="sm" disabled={upsert.isPending}>
            {upsert.isPending ? '保存中…' : '保存打分'}
          </Button>
        </form>

        {err && <Hint text={err} isError />}
        {notice && !err && <Hint text={notice} isError={false} />}

        <QueryState
          isLoading={q.isLoading}
          isError={q.isError}
          error={q.error}
          isEmpty={q.data !== undefined && q.data.length === 0}
          emptyLabel="暂无自定义打分"
          emptyHint="在上方选股并打分后，会出现在这里"
        >
          <ul className="space-y-1">
            {q.data?.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-x-3 text-body">
                <span className="font-medium text-sf-ink">{item.stock_code}</span>
                {item.stock_name && <span className="text-sf-ink-2">{item.stock_name}</span>}
                <span className="text-sf-ink">{item.score} 分</span>
                <span className="text-label text-sf-ink-3">更新：{item.updated_at === null ? '—' : item.updated_at}</span>
                <InlineDeleteConfirm
                  label={`打分 ${item.stock_code}`}
                  pending={del.isPending}
                  confirming={confirmingDeleteCode === item.stock_code}
                  onRequest={() => { resetMessages(); setConfirmingDeleteCode(item.stock_code) }}
                  onCancel={() => setConfirmingDeleteCode(null)}
                  onConfirm={() => {
                    del.mutate({ code: item.stock_code }, {
                      onSuccess: () => { setNotice(`已删除 ${item.stock_code} 的打分`); setConfirmingDeleteCode(null) },
                    })
                  }}
                />
              </li>
            ))}
          </ul>
        </QueryState>
      </div>
    </Card>
  )
}

export function WatchWritePanels() {
  return (
    <div className="space-y-4">
      <WatchlistPanel />
      <JunkStockPanel />
      <UserScorePanel />
    </div>
  )
}
