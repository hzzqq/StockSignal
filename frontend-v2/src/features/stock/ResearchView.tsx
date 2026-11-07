import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import type { StockKline } from '@/api/schemas/stock'
import type { ResearchView as ViewMode, ResearchRouteSearch } from '@/lib/deeplink'
import { useStockKline } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { fmtNum } from '@/lib/format'

/**
 * W4-B · 个股研究页（/stock/research，旧 24 页）。
 * 数据源：getStockKline（/api/v2/read/stock-kline），仅 quick 子视图用；本轮不做 ECharts K 线图（W4-C）。
 *
 * 首帧预选：view 由 validateSearch 归一后的 search.view 经 useState 初始值决定（不用 useEffect），
 * 缺/非法 → quick；code 输入框缺 code → 默认 600519，非 6 位 → 校验提示且不发请求（hook enabled=false）。
 * 诚实红线：rows 空 → EmptyState、date:null →「暂无权威数据日」（禁当前日期兜底）、note 原文展示；
 * deep 子视图如实说明「待 W4-C 迁移」，不造假数据、不画空图表。
 */
const CODE_RE = /^\d{6}$/
const DEFAULT_CODE = '600519'

export interface ResearchViewProps {
  /** 来自 validateSearch 的 {view?, code?}；全 optional，E2E 可直接传字面量。 */
  search?: ResearchRouteSearch
}

export function ResearchView({ search }: ResearchViewProps) {
  const [view, setView] = useState<ViewMode>(() =>
    search?.view === 'deep' ? 'deep' : 'quick',
  )
  const initialCode =
    search?.code && CODE_RE.test(search.code) ? search.code : DEFAULT_CODE
  const [input, setInput] = useState(initialCode)

  const valid = CODE_RE.test(input)
  const kline = useStockKline(input)
  // 反向出边携带当前有效代码（非法输入时回落到初始预选值），不把非法 code 写进 URL。
  const linkCode = valid ? input : initialCode

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">个股研究</h2>
        <span className="text-label text-sf-ink-3">数据源 stock-kline</span>
        <Link
          to="/stock/fundamentals"
          search={{ code: linkCode }}
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          {`← 返回基本面分析（${linkCode}）`}
        </Link>
      </div>

      {/* 分段 radiogroup：原生 button 键盘可达，aria-checked 标注当前视图。 */}
      <div role="radiogroup" aria-label="研究视图" className="flex flex-wrap gap-2">
        <button
          type="button"
          role="radio"
          aria-checked={view === 'quick'}
          onClick={() => setView('quick')}
          className={`rounded-tile border px-4 py-2 text-body ${
            view === 'quick'
              ? 'border-sf-line bg-sf-surface-2 text-sf-ink'
              : 'border-sf-line bg-sf-surface text-sf-ink-3'
          }`}
        >
          ⚡ 快速选取
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={view === 'deep'}
          onClick={() => setView('deep')}
          className={`rounded-tile border px-4 py-2 text-body ${
            view === 'deep'
              ? 'border-sf-line bg-sf-surface-2 text-sf-ink'
              : 'border-sf-line bg-sf-surface text-sf-ink-3'
          }`}
        >
          🔬 深度分析
        </button>
      </div>

      {/* 代码输入：非 6 位仅给校验提示，不发请求（useStockKline enabled=false）。 */}
      <label className="flex flex-wrap items-center gap-3 text-body">
        <span className="text-label text-sf-ink-3">股票代码</span>
        <input
          type="text"
          inputMode="numeric"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          aria-invalid={!valid}
          aria-label="股票代码"
          className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-2 text-body text-sf-ink tabular-nums"
        />
        <span className="text-label text-sf-ink-3">{`当前代码：${linkCode}`}</span>
      </label>

      {view === 'quick' ? (
        <QuickView kline={kline} valid={valid} />
      ) : (
        <DeepView code={linkCode} />
      )}
    </div>
  )
}

function QuickView({
  kline,
  valid,
}: {
  kline: ReturnType<typeof useStockKline>
  valid: boolean
}) {
  if (!valid) {
    return (
      <div role="status" className="text-body text-sf-warn">
        请输入 6 位数字股票代码后再查询
      </div>
    )
  }
  return (
    <Card title="K 线 OHLC 数据表（daily）">
      {/* date 为权威数据日：为 null 时如实显示，禁止今天日期兜底。 */}
      {kline.data && (
        <div className="flex flex-wrap items-center gap-3 text-body mb-3">
          <span className="text-label text-sf-ink-3">数据日</span>
          {kline.data.date === null ? (
            <span role="status" className="text-sf-warn">暂无权威数据日</span>
          ) : (
            <span className="text-sf-ink tabular-nums">{`权威数据日：${kline.data.date}`}</span>
          )}
        </div>
      )}
      <QueryState
        isLoading={kline.isLoading}
        isError={kline.isError}
        error={kline.error}
        isEmpty={!!kline.data && kline.data.rows.length === 0}
        emptyLabel="暂无 K 线数据"
        emptyHint="rows 为空数组，未做填充"
      >
        {kline.data && kline.data.rows.length > 0 ? (
          <KlineTable rows={kline.data.rows} />
        ) : null}
      </QueryState>
      {/* note 为后端原文，原样展示。 */}
      {kline.data && kline.data.note !== null && (
        <p className="text-body text-sf-ink-2 mt-3">{kline.data.note}</p>
      )}
    </Card>
  )
}

/** OHLC 列来自后端英文列名，判空后再取首行 keys 渲染，不做重排。 */
function KlineTable({ rows }: { rows: StockKline['rows'] }) {
  const cols = rows.length > 0 ? Object.keys(rows[0]) : []
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-body border-collapse">
        <caption className="sr-only">日线 OHLC 明细，列名来自后端原始响应，未做重排</caption>
        <thead>
          <tr className="text-label text-sf-ink-3 border-b border-sf-line">
            {cols.map((c) => (
              <th key={c} scope="col" className="text-left py-2 pr-3 font-normal">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="text-sf-ink-2">
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-sf-line last:border-0">
              {cols.map((c) => (
                <td key={c} className="py-1.5 pr-3 tabular-nums">{fmtNum(r[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** deep 子视图：如实说明待 W4-C 迁移，仅显示已预选 code，不造假数据、不画空图表。 */
function DeepView({ code }: { code: string }) {
  return (
    <Card title="深度分析">
      <div className="flow">
        <p className="text-body text-sf-ink-2">
          深度分析子视图待 W4-C 迁移，当前仅完成深链预选
        </p>
        <p className="text-label text-sf-ink-3">{`已预选 code：${code}`}</p>
      </div>
    </Card>
  )
}
