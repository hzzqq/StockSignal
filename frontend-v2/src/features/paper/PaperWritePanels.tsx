import { useState, type FormEvent } from 'react'
import {
  useAddPaperTrade,
  useDeletePaperTrade,
  useResetPaperBook,
} from '@/lib/queriesPatternPaper'
import { usePaperTrades } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'

/**
 * 42 模拟交易写面板（parity C）：把 v1 的模拟账本写能力接进 v2 /paper。
 *
 * 诚实红线：
 *  - 只写本地 paper_<user>.json 账本，绝不触任何券商 / 真实下单；
 *  - 用户取自 JWT，不接受 body 传入用户名冒充他人账本；
 *  - 删除成交记录只删记录、不回滚现金/持仓，UI 明示该语义；
 *  - 校验失败 422 如实展示后端消息，不吞错、不谎称成功。
 */
const INPUT_CLS =
  'mt-1 w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent'
const BTN_CLS =
  'rounded-tile border border-sf-line px-3 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-50'
const LABEL_CLS = 'block text-label text-sf-ink-3'

function firstError(e: unknown): string | null {
  return e instanceof Error ? e.message : null
}

export function PaperWritePanels() {
  const [user] = useState('admin') // 只读展示当前查看的账本；写操作的用户由 JWT 决定
  const q = usePaperTrades(user)
  const addM = useAddPaperTrade()
  const delM = useDeletePaperTrade()
  const resetM = useResetPaperBook()

  const [code, setCode] = useState('600519')
  const [side, setSide] = useState<'买' | '卖'>('买')
  const [price, setPrice] = useState('1500')
  const [qty, setQty] = useState('100')
  const [notice, setNotice] = useState<string | null>(null)

  function submitTrade(e: FormEvent) {
    e.preventDefault()
    setNotice(null)
    addM.reset()
    const p = Number(price)
    const n = Number(qty)
    if (!/^\d{6}$/.test(code) || !Number.isFinite(p) || p <= 0 ||
        !Number.isInteger(n) || n < 100 || n % 100 !== 0) {
      setNotice('代码须 6 位、价格为有限正数、数量为 100 的整数倍（≥100）')
      return
    }
    addM.mutate(
      { code, side, price: p, qty: n },
      { onSuccess: () => setNotice(`已记录模拟${side} ${code} × ${n}`) },
    )
  }

  const addError = firstError(addM.error)
  const delError = firstError(delM.error)
  const resetError = firstError(resetM.error)
  const trades = Array.isArray(q.data?.trades) ? q.data.trades : []

  return (
    <div className="space-y-4">
      <Card title="记一笔模拟成交">
        <form onSubmit={submitTrade} className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-4">
            <label className={LABEL_CLS}>
              代码
              <input aria-label="模拟成交代码" value={code}
                onChange={(e) => setCode(e.target.value)} className={INPUT_CLS} />
            </label>
            <label className={LABEL_CLS}>
              方向
              <select aria-label="模拟成交方向" value={side}
                onChange={(e) => setSide(e.target.value as '买' | '卖')} className={INPUT_CLS}>
                <option value="买">买入</option>
                <option value="卖">卖出</option>
              </select>
            </label>
            <label className={LABEL_CLS}>
              价格
              <input aria-label="模拟成交价格" type="number" step="0.01" value={price}
                onChange={(e) => setPrice(e.target.value)} className={INPUT_CLS} />
            </label>
            <label className={LABEL_CLS}>
              数量（100 倍数）
              <input aria-label="模拟成交数量" type="number" step="100" value={qty}
                onChange={(e) => setQty(e.target.value)} className={INPUT_CLS} />
            </label>
          </div>
          <button type="submit" disabled={addM.isPending} className={BTN_CLS}>
            {addM.isPending ? '记录中…' : '记录模拟成交'}
          </button>
          {notice && !addError && <span className="ml-2 text-label text-sf-ink-2">{notice}</span>}
          {addError && <span className="ml-2 text-label text-sf-danger">保存失败：{addError}</span>}
        </form>
      </Card>

      <Card title="成交记录（删除仅删记录，不回滚现金/持仓）">
        {trades.length === 0 ? (
          <p className="text-xs text-sf-ink-3">该账本暂无成交记录。</p>
        ) : (
          <ul className="space-y-1 text-label">
            {trades.map((t, i) => (
              <li
                key={t.id != null ? `id-${t.id}` : `hist-${i}-${String(t.time ?? '')}-${String(t.code ?? '')}`}
                className="flex items-center justify-between gap-2 border-b border-sf-line py-1"
              >
                <span>
                  {String(t.time ?? '')} · {String(t.code ?? '')} · {String(t.side ?? '')}
                  {' '}{String(t.qty ?? '')} 股 @ {String(t.price ?? '')}
                </span>
                {typeof t.id === 'number' && Number.isInteger(t.id) ? (
                  <button
                    type="button"
                    disabled={delM.isPending}
                    onClick={() => {
                      setNotice(null)
                      delM.reset()
                      delM.mutate(t.id as number, {
                        onSuccess: () => setNotice(`已删除记录 ${t.id}`),
                      })
                    }}
                    className={BTN_CLS}
                  >
                    删除
                  </button>
                ) : (
                  <span className="text-label text-sf-ink-3">历史记录无 id，不可删</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {delError && <p className="mt-1 text-label text-sf-danger">删除失败：{delError}</p>}
      </Card>

      <Card title="重置模拟账本">
        <button
          type="button"
          disabled={resetM.isPending}
          onClick={() => {
            setNotice(null)
            resetM.reset()
            resetM.mutate(undefined, { onSuccess: () => setNotice('模拟账本已重置') })
          }}
          className={BTN_CLS}
        >
          {resetM.isPending ? '重置中…' : '重置为初始资金'}
        </button>
        {resetError && <span className="ml-2 text-label text-sf-danger">重置失败：{resetError}</span>}
      </Card>
    </div>
  )
}
