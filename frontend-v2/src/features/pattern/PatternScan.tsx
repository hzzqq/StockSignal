import { useState, type FormEvent } from 'react'
import { usePatternScan } from './usePatternScan'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'
import type { PatternItem } from '@/api/schemas/patternScan'

/**
 * 31 形态选股（parity C）：把 v1 pages/31_形态选股.py 的高级形态识别算法
 * 后端化为纯函数，v2 只做诚实渲染与提交，不自己识别形态、不编造信号。
 *
 * 诚实红线：
 *  - 走异步任务（POST /api/v2/pattern-scan/tasks → 轮询 GET /api/tasks/<id>），
 *    切页不打断，同会话切回结果仍在；结果为内存态，刷新即清；
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
  /** 搜索选中的股票名称回显（code -> name）；手输代码无名称，显示"—"不臆造。 */
  const [names, setNames] = useState<Record<string, string>>({})
  const { phase, progress, result, error, submit, requery, reset } = usePatternScan()
  const codes = parseCodes(raw)
  const running = phase === 'submitting' || phase === 'polling'

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!codes || running) return
    void submit(codes)
  }

  /** 搜索追加：去重后写回批量输入框；名称仅作展示，不进扫描请求。 */
  function appendStock(code: string, item: { name?: string } | null) {
    const current = parseCodes(raw) ?? []
    if (current.includes(code)) return
    setRaw((current.length ? [...current, code] : [code]).join(', '))
    if (item?.name) setNames((m) => ({ ...m, [code]: item.name as string }))
  }

  return (
    <div className="space-y-4">
      <SectionTitle as="h2">技术形态扫描</SectionTitle>
      <p className="text-xs text-sf-ink-3">
        {`在给定股票池上识别 MACD / 均线 / KDJ 金叉死叉与顶底背离（来自 v1 31 页的离线纯函数算法）。 形态是历史技术描述，`}
        <LeadText>不是收益预测，也不构成投资建议</LeadText>
        {`。 扫描以后台任务运行，切页不打断；结果为本次会话内存态，页面刷新后清空。`}
      </p>

      <Card title="扫描池">
        <form onSubmit={onSubmit} className="space-y-2">
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

          {/* 统一股票搜索：代码 / 名称 / 拼音首字母召回，选中即追加到扫描池（去重）。
              与批量手输共存——手输适合粘贴清单，搜索适合按名称查找，不破坏原语义。 */}
          <div className="pt-1">
            <div className="w-72">
              <StockSearchInput
                label="搜索追加扫描标的（代码 / 名称 / 首字母）"
                placeholder="搜索后追加到扫描池，如 600519、茅台、gzmt"
                onSelect={appendStock}
              />
            </div>
            {codes && codes.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="已选扫描标的">
                {codes.map((code) => (
                  <li
                    key={code}
                    className="rounded-tile border border-sf-line px-2 py-0.5 text-label text-sf-ink-2"
                  >
                    {code}
                    {names[code] ? ` ${names[code]}` : ''}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!codes || running}
          >
            {phase === 'submitting'
              ? '提交中…'
              : phase === 'polling'
                ? `扫描中…（后台任务运行${progress > 0 ? `，已完成约 ${Math.round(progress)}%` : ''}）`
                : '开始形态扫描'}
          </Button>
        </form>
      </Card>

      {phase === 'error' && (
        <Card title="扫描未完成">
          <p className="text-xs text-sf-danger" role="alert">{error ?? '扫描失败'}</p>
        </Card>
      )}

      {phase === 'timeout' && (
        <Card title="等待超时">
          <p className="text-xs text-sf-ink-2" role="status">
            前端等待超时（上限 120s）。任务并未失败，仍在后台运行；结果不会自动推送，可稍后点击
            「重新查询结果」接续查看（不重复提交）。
          </p>
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={requery}
            >
              重新查询结果
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={reset}
            >
              放弃本次，重新填写
            </Button>
          </div>
        </Card>
      )}

      {phase !== 'done' || !result ? null : (
        <div className="space-y-3">
          <p className="text-label text-sf-ink-3">
            已扫描 {result.n_scanned} 只 · {result.available ? '结果如下' : '整体不可用'}
            {result.reason ? `：${result.reason}` : ''}
          </p>
          {result.results.length === 0 ? (
            <p className="text-xs text-sf-ink-3">无可用结果，不伪造形态。</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {result.results.map((r) => (
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

      {phase === 'idle' && (
        <p className="text-xs text-sf-ink-3">尚未扫描或结果不可用。</p>
      )}
    </div>
  )
}
