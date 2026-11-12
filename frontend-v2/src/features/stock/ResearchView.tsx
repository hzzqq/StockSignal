import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import type { StockKline, ResearchDeep } from '@/api/schemas/stock'
import type { ResearchView as ViewMode, ResearchRouteSearch } from '@/lib/deeplink'
import { useStockIntraday, useStockKline } from '@/lib/queries'
import { getResearchDeep } from '@/api/stock'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { inkForCell } from '@/lib/domainColor'
import { fmtNum } from '@/lib/format'
import { KLineChart } from './charts/KLineChart'
import { IntradayChart } from './charts/IntradayChart'

/**
 * W4-B · 个股研究页（/stock/research，旧 24 页）。
 * 数据源：getStockKline（/api/v2/read/stock-kline）+ getStockIntraday
 * （/api/v2/read/stock-intraday，含昨收基准 prev_close），仅 quick 子视图用。
 *
 * 首帧预选：view 由 validateSearch 归一后的 search.view 经 useState 初始值决定（不用 useEffect），
 * 缺/非法 → quick；code 输入框缺 code → 默认 600519，非 6 位 → 校验提示且不发请求（hook enabled=false）。
 * 诚实红线：rows 空 → EmptyState、date:null →「暂无权威数据日」（禁当前日期兜底）、note 原文展示；
 * 分时数据源独立四态（加载 / 失败 / rows=[] / 有数据）均显式渲染，绝不静默省略整块；
 * deep 子视图调 getResearchDeep 渲染技术字段表（域级双色），deep_analysis_available===false 显豁免卡，
 * 不造假数据、不画空图表。
 *
 * 涨跌色口径：个股页价格域 = 报告体语义（涨绿跌红），由 priceDomain="report" 显式注入
 * （DESIGN.md §3/§6.2「K线阴阳线：按 priceDomain 注入，报告体页面不得沿用交易屏红涨绿跌」）。
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
        <QuickView kline={kline} valid={valid} code={input} />
      ) : (
        <DeepView code={linkCode} />
      )}
    </div>
  )
}

function QuickView({
  kline,
  valid,
  code,
}: {
  kline: ReturnType<typeof useStockKline>
  valid: boolean
  code: string
}) {
  const intraday = useStockIntraday(code)
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
        {/* K 线主图（蜡烛 + MA + 成交量 + MACD），复用 KLineChart；报告体价格域（绿涨红跌）。 */}
        {kline.data && kline.data.rows.length > 0 && (
          <KLineChart rows={kline.data.rows} priceDomain="report" />
        )}
        {/* 分时主图（价格线 + 均价线 + 昨收基准 + 成交量），复用 IntradayChart；
            报告体价格域（绿涨红跌）；prev_close 取不到时组件内部诚实标注「暂无昨收基准」。
            诚实红线：分时是独立数据源，加载 / 失败 / 空数组都必须显式告知，
            不得像「页面本来就没有这块」一样静默省略（§30 DataExport 同族）。
            后端契约 read_routes.py::stock_intraday：无数据 = status ok + rows=[] + date=null，
            故 rows=[] 走空态；isError 走错误态，绝不把失败伪装成无数据。 */}
        <div className="mt-4" data-testid="intraday-section">
          <div className="text-label text-sf-ink-3 mb-2">分时走势</div>
          <QueryState
            isLoading={intraday.isLoading}
            isError={intraday.isError}
            error={intraday.error}
            isEmpty={!intraday.data || intraday.data.rows.length === 0}
            emptyLabel="暂无分时数据"
            emptyHint="分时 rows 为空数组，未做填充或补零"
          >
            {intraday.data && intraday.data.rows.length > 0 ? (
              <IntradayChart
                rows={intraday.data.rows}
                prevClose={intraday.data.prev_close}
                priceDomain="report"
              />
            ) : null}
          </QueryState>
        </div>
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

/**
 * deep 子视图（W4-C 迁移后真实内容）：调 getResearchDeep（/v2/read/research-deep，
 * 56 键深度分析通用透传），渲染 price/pe_ttm/pb/market_cap/ma5/ma10/ma20/ma60/
 * amplitude/turnover 等技术字段表，按 domainInk 域级双色。
 *
 * 诚实豁免卡：若返回 deep_analysis_available === false（或该字段缺失且无任何技术字段），
 * 显示明确说明「56 键深度分析（旧版 analysis_engine 异步任务）V2 暂未接入，可走 /legacy
 * 查看旧版」，绝不造假数据、不画空图表。
 */
const DEEP_META = new Set(['code', 'name', 'industry', 'date', 'note', 'period', 'deep_analysis_available'])

/** deep 子视图是否处于「明确未接入」豁免态：deep_analysis_available===false，
 * 或字段缺失且无任何技术字段（无法确认已接入）。与 DeepBody 内判定保持一致，
 * 防止 QueryState 的 isEmpty 把豁免卡误判为空而整体隐藏。 */
function isDeepExempt(d: ResearchDeep | null | undefined): boolean {
  if (!d) return false
  const available = d['deep_analysis_available']
  const techKeys = Object.keys(d).filter((k) => !DEEP_META.has(k))
  return available === false || (available === undefined && techKeys.length === 0)
}

function DeepView({ code }: { code: string }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['read', 'research-deep', code],
    queryFn: () => getResearchDeep(code),
    enabled: /^\d{6}$/.test(code),
    staleTime: 5 * 60_000,
  })

  return (
    <Card title="深度分析">
      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={error}
        isEmpty={!!data && Object.keys(data).filter((k) => !DEEP_META.has(k)).length === 0 && !isDeepExempt(data)}
        emptyLabel="暂无深度数据"
        emptyHint="该股票未返回任何技术字段"
      >
        {data ? <DeepBody data={data} /> : null}
      </QueryState>
    </Card>
  )
}

function DeepBody({ data }: { data: ResearchDeep }) {
  const techKeys = Object.keys(data).filter((k) => !DEEP_META.has(k))
  // 豁免：明确 false，或字段缺失且无任何技术字段（无法确认已接入）。
  const exempt = isDeepExempt(data)

  if (exempt) {
    return (
      <div className="flow">
        <p className="text-body text-sf-ink-2">
          56 键深度分析（旧版 analysis_engine 异步任务）V2 暂未接入，可走 /legacy 查看旧版
        </p>
        <p className="text-label text-sf-ink-3">{`已预选 code：${String(data['code'] ?? '')}`}</p>
      </div>
    )
  }

  if (techKeys.length === 0) {
    return (
      <div role="status" className="py-10 text-center text-body text-sf-ink-2">
        暂无深度数据
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-body border-collapse">
        <caption className="sr-only">个股深度技术字段，列名取后端原始响应 key，未做重排</caption>
        <thead>
          <tr className="text-label text-sf-ink-3 border-b border-sf-line">
            <th scope="col" className="text-left py-2 pr-3 font-normal">字段</th>
            <th scope="col" className="text-left py-2 pr-3 font-normal tabular-nums">数值</th>
          </tr>
        </thead>
        <tbody className="text-sf-ink-2">
          {techKeys.map((k) => {
            const v = (data as Record<string, unknown>)[k]
            return (
              <tr key={k} className="border-b border-sf-line last:border-0">
                <th
                  scope="row"
                  className="text-left py-1.5 pr-3 font-normal text-sf-ink-3"
                  style={{ color: inkForCell(k, undefined) }}
                >
                  {k}
                </th>
                <td
                  className="py-1.5 pr-3 tabular-nums"
                  style={typeof v === 'number' ? { color: inkForCell(k, v) } : undefined}
                >
                  {fmtNum(v)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
