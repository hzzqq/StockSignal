import { useState, type FormEvent } from 'react'
import {
  usePatternScanMutation,
} from '@/lib/queriesPatternPaper'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import type { PatternItem } from '@/api/schemas/patternScan'

/**
 * 31 形态选股（parity C）：把 v1 pages/31_形态选股.py 的高级形态识别算法
 * 后端化为纯函数，v2 只做诚实渲染与提交，不自己识别形态、不编造信号。
 *
 * 诚实红线：
 *  - 单股失败 available=false + reason 原样透出，不补 0 / 不伪造形态；
 *  - 历史统计与形态信号是技术形态描述，不是收益预测；
 *  - 不触任何实盘交易能力。
 */
// 形态方向是技术描述，不是价格/盈亏；用中性色 + 形状，禁借涨跌色 Tailwind class
const BIAS_LABEL: Record<string, string> = {
  看涨: '▲ 看涨',
  看跌: '▼ 看跌',
}

function parseCodes(raw: string): string[] | null {
  const codes = raw
    .split(/[\s,，;；]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (codes.length < 1 || codes.length > 50) return null
  if (!codes.every((c) => /^\d{6}$/.test(c))) return null
  return codes
}

export function PatternScan() {
  const [raw, setRaw] = useState('600519, 000001')
  const scan = usePatternScanMutation()
  const codes = parseCodes(raw)

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!codes) return
    scan.reset()
    scan.mutate({ codes })
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">技术形态扫描</h2>
      <p className="text-xs text-sf-ink-3">
        在给定股票池上识别 MACD / 均线 / KDJ 金叉死叉与顶底背离（来自 v1 31 页的离线纯函数算法）。
        形态是历史技术描述，不是收益预测，也不构成投资建议。
      </p>

      <Card title="扫描池">
        <form onSubmit={submit} className="space-y-2">
          <label className="block text-label text-sf-ink-3">
            股票代码（6 位，逗号 / 空格分隔，1–50 只）
            <input
              aria-label="形态扫描股票代码"
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              className="mt-1 w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
            />
          </label>
          {raw.trim() && !codes && (
            <span className="text-label text-sf-danger">代码格式不合法，未发起扫描</span>
          )}
          <button
            type="submit"
            disabled={!codes || scan.isPending}
            className="rounded-tile border border-sf-line px-3 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-50"
          >
            {scan.isPending ? '扫描中…' : '开始形态扫描'}
          </button>
        </form>
      </Card>

      <QueryState
        isLoading={scan.isPending}
        isError={scan.isError}
        error={scan.error}
        isEmpty={!scan.data}
        emptyLabel={scan.data ? undefined : '尚未扫描或结果不可用'}
      >
        {scan.data && (
          <div className="space-y-3">
            <p className="text-label text-sf-ink-3">
              已扫描 {scan.data.n_scanned} 只 · {scan.data.available ? '结果如下' : '整体不可用'}
              {scan.data.reason ? `：${scan.data.reason}` : ''}
            </p>
            {scan.data.results.length === 0 ? (
              <p className="text-xs text-sf-ink-3">无可用结果，不伪造形态。</p>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {scan.data.results.map((r) => (
                  <Card
                    key={r.code}
                    title={`${r.code}${r.name ? ` · ${r.name}` : ''}`}
                  >
                    {!r.available ? (
                      <p className="text-xs text-sf-ink-3">
                        {r.reason ?? '该标的形态数据不可用'}（样本 {r.n_bars} 根）
                      </p>
                    ) : r.patterns.length === 0 ? (
                      <p className="text-xs text-sf-ink-3">近窗口未命中形态（样本 {r.n_bars} 根）。</p>
                    ) : (
                      <ul className="space-y-1 text-label">
                        {r.patterns.map((p: PatternItem, i) => (
                          <li key={`${p.name}-${p.bias}-${i}`} className="flex justify-between gap-2">
                            <span>{p.date} · {p.name}</span>
                            <span className="text-sf-ink-2">{BIAS_LABEL[p.bias] ?? p.bias}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}
      </QueryState>
    </div>
  )
}
