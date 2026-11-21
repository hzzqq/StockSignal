import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { EChartsOption } from 'echarts'
import type { Portfolio as PortfolioData, PositionAllocation } from '@/api/schemas/read'
import { usePortfolio, usePositionAllocation } from '@/lib/queries'
import { addPortfolioPosition, deletePortfolioPosition, recordPortfolioSell } from '@/api/portfolioWrite'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { ErrorState, QueryState } from '@/shared/ui/States'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 45 页「持仓中心」V2 化落地（对应 IA-MIGRATION.md Tier1）。
 * 数据来源：usePortfolio → GET /api/v2/read/portfolio（backend 复用
 * modules.portfolio.PortfolioManager，本地 data/portfolio.csv 模拟持仓）。
 *
 * 三态：加载中 / 取数失败（error）/ 无持仓（empty）。
 * 分段：持仓（逐批盈亏表）/ 收益归因（贡献条形 + 权重条形 + 净值曲线）。
 *
 * ⚠️ 诚实红线（DESIGN.md / modules.portfolio）：
 *  - 持仓为本地模拟/历史数据，仅供学习；现价离线口径可能为静态样本，页脚原样带出后端 note；
 *  - 净值曲线为尽力而为的历史还原，curve_available=false 时如实标注、不补零曲线；
 *  - NaN/Inf 后端已清洗为 null，缺值显示「—」，绝不补 0。
 */
type View = 'positions' | 'attribution' | 'landing'
type AllocSource = 'recommend' | 'user' | 'equal'

function f2(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—'
}
function pct(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(2)}%` : '—'
}
function pnlColor(v: unknown): string | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? (v >= 0 ? CHART.up : CHART.down) : undefined
}

export function Portfolio() {
  const [view, setView] = useState<View>('positions')
  const [source, setSource] = useState<AllocSource>('recommend')
  const q = usePortfolio()
  const data = q.data

  return (
    <div className="flow">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-lg font-semibold">持仓中心</h2>
        <div className="flex gap-1 rounded-tile bg-sf-surface-2 p-1 text-xs">
          <button
            type="button"
            onClick={() => setView('positions')}
            className={`rounded-tile px-3 py-1.5 ${view === 'positions' ? 'bg-sf-accent text-sf-ink' : 'text-sf-ink-3'}`}
          >
            持仓
          </button>
          <button
            type="button"
            onClick={() => setView('attribution')}
            className={`rounded-tile px-3 py-1.5 ${view === 'attribution' ? 'bg-sf-accent text-sf-ink' : 'text-sf-ink-3'}`}
          >
            收益归因
          </button>
          <button
            type="button"
            onClick={() => setView('landing')}
            className={`rounded-tile px-3 py-1.5 ${view === 'landing' ? 'bg-sf-accent text-sf-ink' : 'text-sf-ink-3'}`}
          >
            决策落地
          </button>
        </div>
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && (!data.positions || data.positions.length === 0)}
        emptyLabel="暂无持仓数据"
        emptyHint="本地持仓文件为空或缺失（后端 honest 降级）"
      >
        {data ? (
          view === 'positions' ? (
            <PositionsView data={data} />
          ) : view === 'attribution' ? (
            <AttributionView data={data} />
          ) : (
            <LandingView source={source} setSource={setSource} />
          )
        ) : null}
      </QueryState>
    </div>
  )
}

/** 本地模拟账本写面板：添加持仓 / 记录卖出 / 按行号删除，写完精确失效组合查询。 */
function PortfolioWritePanel({ positions }: {
  positions: Array<{
    ticker: string
    name?: string | null
    buy_price?: number | null
    remaining_shares?: number | null
  }>
}) {
  const qc = useQueryClient()
  const [addCode, setAddCode] = useState('')
  const [addName, setAddName] = useState('')
  const [addDate, setAddDate] = useState('')
  const [addPrice, setAddPrice] = useState('')
  const [addShares, setAddShares] = useState('')
  const [addNote, setAddNote] = useState('')
  const [sellCode, setSellCode] = useState('')
  const [sellName, setSellName] = useState('')
  const [sellDate, setSellDate] = useState('')
  const [sellPrice, setSellPrice] = useState('')
  const [sellShares, setSellShares] = useState('')
  const [sellNote, setSellNote] = useState('')

  const invalidate = () => { void qc.invalidateQueries({ queryKey: ['read', 'portfolio'] }) }
  const addMut = useMutation({ mutationFn: addPortfolioPosition, onSuccess: invalidate })
  const sellMut = useMutation({ mutationFn: recordPortfolioSell, onSuccess: invalidate })
  const error = addMut.error ?? sellMut.error
  const errorText = error instanceof Error ? error.message : error ? '写入失败' : null

  return (
    <Card title="模拟账本写操作" right={<span className="text-label text-sf-ink-3">本地 CSV · 全站共享 · 非实盘</span>}>
      <div className="grid md:grid-cols-2 gap-4">
        <form
          className="flow"
          onSubmit={(e) => {
            e.preventDefault()
            addMut.mutate({
              ticker: addCode, buy_date: addDate,
              buy_price: Number(addPrice), shares: Number(addShares),
              name: addName || undefined, note: addNote || undefined,
            })
          }}
        >
          <div className="text-body text-sf-ink-2">添加持仓</div>
          <StockSearchInput
            value={addCode}
            label="股票代码"
            onTextChange={setAddCode}
            onSelect={(code, item) => { setAddCode(code); if (item?.name) setAddName(item.name) }}
          />
          <input aria-label="股票名称" value={addName} onChange={(e) => setAddName(e.target.value)}
            placeholder="股票名称（可不填，留空用代码）" className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="买入日期" type="date" value={addDate} onChange={(e) => setAddDate(e.target.value)}
            className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="买入价" type="number" step="0.01" min="0.01" value={addPrice}
            onChange={(e) => setAddPrice(e.target.value)} placeholder="买入价"
            className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="买入股数" type="number" step="100" min="1" value={addShares}
            onChange={(e) => setAddShares(e.target.value)} placeholder="买入股数"
            className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="买入备注" value={addNote} onChange={(e) => setAddNote(e.target.value)}
            placeholder="备注（选填）" className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <button type="submit" disabled={addMut.isPending}
            className="w-fit rounded-tile bg-sf-accent px-3 py-1.5 text-xs text-white disabled:opacity-50">
            {addMut.isPending ? '写入中…' : '添加持仓'}
          </button>
        </form>

        <form
          className="flow"
          onSubmit={(e) => {
            e.preventDefault()
            sellMut.mutate({
              ticker: sellCode, sell_date: sellDate,
              sell_price: Number(sellPrice), sell_shares: Number(sellShares),
              name: sellName || undefined, note: sellNote || undefined,
            })
          }}
        >
          <div className="text-body text-sf-ink-2">记录卖出</div>
          <StockSearchInput
            value={sellCode}
            label="卖出股票代码"
            onTextChange={setSellCode}
            onSelect={(code, item) => { setSellCode(code); if (item?.name) setSellName(item.name) }}
          />
          <input aria-label="卖出股票名称" value={sellName} onChange={(e) => setSellName(e.target.value)}
            placeholder="股票名称（可不填）" className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="卖出日期" type="date" value={sellDate} onChange={(e) => setSellDate(e.target.value)}
            className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="卖出价" type="number" step="0.01" min="0.01" value={sellPrice}
            onChange={(e) => setSellPrice(e.target.value)} placeholder="卖出价"
            className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="卖出股数" type="number" step="100" min="1" value={sellShares}
            onChange={(e) => setSellShares(e.target.value)} placeholder="卖出股数"
            className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <input aria-label="卖出备注" value={sellNote} onChange={(e) => setSellNote(e.target.value)}
            placeholder="备注（选填）" className="w-full rounded-tile border border-sf-line px-2 py-1 text-xs" />
          <button type="submit" disabled={sellMut.isPending}
            className="w-fit rounded-tile bg-sf-accent px-3 py-1.5 text-xs text-white disabled:opacity-50">
            {sellMut.isPending ? '写入中…' : '记录卖出'}
          </button>
        </form>
      </div>
      <p className="text-label text-sf-ink-3 mt-3">
        明细表的「删除」按钮按当前表格行号删除本地模拟记录（行号与后端一致）；卖出只追加交易记录，不改买入批次。
        {positions.length ? ` 当前 ${positions.length} 批。` : ''}
      </p>
      {errorText ? <ErrorState message={errorText} /> : null}
    </Card>
  )
}

/** 按行号删除本地模拟持仓：行号取自 /portfolio 数组下标，与后端同源。 */
function DeletePositionButton({ index, ticker }: { index: number; ticker: string }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const mut = useMutation({
    mutationFn: deletePortfolioPosition,
    onSuccess: () => {
      setError(null)
      void qc.invalidateQueries({ queryKey: ['read', 'portfolio'] })
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : '删除失败'),
  })
  return (
    <span className="inline-flex flex-col items-end">
      <button
        type="button"
        aria-label={`删除 ${ticker} 持仓记录`}
        disabled={mut.isPending}
        onClick={() => mut.mutate(index)}
        className="rounded-tile border border-sf-line px-2 py-0.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-50"
      >
        {mut.isPending ? '删除中' : '删除'}
      </button>
      {error ? <span role="alert" className="text-label text-sf-danger">{error}</span> : null}
    </span>
  )
}

function PositionsView({ data }: { data: PortfolioData }) {
  const s = data.summary ?? {}
  const positions = data.positions ?? []

  return (
    <div className="space-y-4">
      <PortfolioWritePanel positions={positions} />
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <Stat label="总持仓成本" value={typeof s.total_cost === 'number' ? `¥${s.total_cost.toLocaleString('zh-CN')}` : '—'} />
        <Stat label="总市值" value={typeof s.total_market_value === 'number' ? `¥${s.total_market_value.toLocaleString('zh-CN')}` : '—'} />
        <Stat label="总盈亏" value={pct(s.total_pnl_pct)} color={pnlColor(s.total_pnl)} />
        <Stat label="总盈亏额" value={typeof s.total_pnl === 'number' ? `¥${s.total_pnl.toLocaleString('zh-CN')}` : '—'} color={pnlColor(s.total_pnl)} />
        <Stat label="持仓批数" value={f2(s.position_count)} />
      </div>

      <Card title={`持仓明细（${positions.length} 批）`}>
        {positions.length === 0 ? (
          <div className="text-xs text-sf-ink-3">暂无持仓。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-sf-ink">
              <thead>
                <tr className="text-sf-ink-3 border-b border-sf-line">
                  <th className="text-left py-1.5 pr-3">代码</th>
                  <th className="text-left py-1.5 pr-3">名称</th>
                  <th className="text-right py-1.5 pr-3">买入价</th>
                  <th className="text-right py-1.5 pr-3">现价</th>
                  <th className="text-right py-1.5 pr-3">剩余股数</th>
                  <th className="text-right py-1.5 pr-3">成本</th>
                  <th className="text-right py-1.5 pr-3">市值</th>
                  <th className="text-right py-1.5 pr-3">盈亏额</th>
                  <th className="text-right py-1.5">盈亏%</th>
                  <th className="text-right py-1.5">操作</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={`${p.ticker}-${i}`} className="border-b border-sf-line/60">
                    <td className="py-1.5 pr-3">{p.ticker}</td>
                    <td className="py-1.5 pr-3">{p.name ?? '—'}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.buy_price)}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.current_price)}</td>
                    <td className="py-1.5 pr-3 text-right">{typeof p.remaining_shares === 'number' ? p.remaining_shares.toLocaleString('zh-CN') : '—'}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.cost)}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.market_value)}</td>
                    <td className="py-1.5 pr-3 text-right" style={{ color: pnlColor(p.pnl) }}>
                      {f2(p.pnl)}
                    </td>
                    <td className="py-1.5 text-right" style={{ color: pnlColor(p.pnl_pct) }}>
                      {pct(p.pnl_pct)}
                    </td>
                    <td className="py-1.5 text-right">
                      <DeletePositionButton index={i} ticker={p.ticker} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}

function AttributionView({ data }: { data: PortfolioData }) {
  const attr = data.attribution ?? []
  const weights = data.weights ?? []
  const curve = data.curve ?? []
  const curveAvailable = !!data.curve_available

  const contributionOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 96, right: 24, top: 16, bottom: 24 },
    xAxis: { type: 'value', axisLabel: { color: CHART.ink2, formatter: '{value}%' }, splitLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'category', data: attr.map((a) => a.name ?? a.ticker).reverse(), axisLabel: { color: CHART.ink2 }, axisLine: { lineStyle: { color: CHART.line } } },
    series: [
      {
        type: 'bar',
        data: attr
          .map((a) => ({
            value: typeof a.contribution === 'number' ? a.contribution : null,
            itemStyle: { color: a.contribution == null ? CHART.ink2 : a.contribution >= 0 ? CHART.up : CHART.down },
          }))
          .reverse(),
      },
    ],
  }

  const weightOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 96, right: 24, top: 16, bottom: 24 },
    xAxis: { type: 'value', max: 100, axisLabel: { color: CHART.ink2, formatter: '{value}%' }, splitLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'category', data: weights.map((w) => w.name ?? w.ticker).reverse(), axisLabel: { color: CHART.ink2 }, axisLine: { lineStyle: { color: CHART.line } } },
    series: [{ type: 'bar', data: weights.map((w) => (typeof w.weight_pct === 'number' ? w.weight_pct : null)), itemStyle: { color: CHART.accent } }],
  }

  const dates = curve.map((c) => c.date)
  const pfVals = curve.map((c) => (typeof c.portfolio === 'number' && Number.isFinite(c.portfolio) ? c.portfolio : null))
  const bmVals = curve.map((c) => (typeof c.benchmark === 'number' && Number.isFinite(c.benchmark) ? c.benchmark : null))
  const curveOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['组合净值', '沪深300'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 48, right: 24, top: 28, bottom: 52 },
    dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 6, height: 18 }],
    xAxis: { type: 'category', data: dates, axisLabel: { color: CHART.ink2, hideOverlap: true }, axisLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'value', axisLabel: { color: CHART.ink2 }, splitLine: { lineStyle: { color: CHART.line } } },
    series: [
      { name: '组合净值', type: 'line', smooth: true, showSymbol: false, data: pfVals, itemStyle: { color: CHART.up }, lineStyle: { color: CHART.up, width: 1.5 } },
      { name: '沪深300', type: 'line', smooth: true, showSymbol: false, data: bmVals, itemStyle: { color: CHART.ink2 }, lineStyle: { color: CHART.ink2, width: 1, type: 'dashed' } },
    ],
  }

  return (
    <div className="space-y-4">
      <Card title="盈亏贡献（按个股，红涨绿跌）">
        {attr.length === 0 ? (
          <div className="text-xs text-sf-ink-3">暂无归因数据。</div>
        ) : (
          <EChart option={contributionOption} height={Math.max(160, attr.length * 28)} ariaLabel="盈亏贡献条形图" />
        )}
      </Card>

      <Card title="持仓市值占比">
        {weights.length === 0 ? (
          <div className="text-xs text-sf-ink-3">暂无权重数据。</div>
        ) : (
          <EChart option={weightOption} height={Math.max(160, weights.length * 28)} ariaLabel="持仓市值占比条形图" />
        )}
      </Card>

      <Card title="组合净值曲线（基准沪深300，尽力而为）">
        {curveAvailable && curve.length >= 2 ? (
          <EChart option={curveOption} height={300} ariaLabel="组合净值曲线图，对比沪深300基准" />
        ) : (
          <div className="text-xs text-sf-ink-3">
            净值曲线需要个股日线数据，当前离线口径无法还原（后端诚实降级，不补零）。
          </div>
        )}
      </Card>

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}

const SOURCE_LABELS: Record<AllocSource, string> = {
  recommend: '荐股引擎综合分',
  user: '用户 StockScore',
  equal: '等权（明示降级）',
}

/**
 * 决策落地（98 页 V2 化，纯建议层只读卡片）。
 *
 * 数据：usePositionAllocation(source) → GET /api/v2/read/position-allocation。
 * 把「市场仓位（当日快照）× 个股评分」落为个股目标权重。
 *
 * ⚠️ 诚实红线（同 v1 98 页）：
 *  - 纯建议层：系统不会自动下单，也绝不写入持仓记录（portfolio.csv 只读不碰）；
 *  - 市场仓位/评分源不可得 → 后端返回 unavailable（前端 error 态），不实时臆算；
 *  - 评分缺失标的剔除并注明，绝不编造；等权＝明示降级（无评分源可用）。
 */
function LandingView({ source, setSource }: { source: AllocSource; setSource: (s: AllocSource) => void }) {
  const q = usePositionAllocation(source)
  const data = q.data

  return (
    <div className="space-y-4">
      <div className="rounded-tile bg-sf-surface-2 px-3 py-2 text-xs text-sf-ink-3">
        🚦 <span className="font-medium text-sf-ink">建议 ≠ 交易</span>：本卡片只产出「目标权重」参考，
        系统不会自动下单，也绝不写入你的持仓记录（只读不碰）。数据源 = 当日归档快照，无快照不实时臆算。
      </div>

      <div className="flex gap-1 rounded-tile bg-sf-surface-2 p-1 text-xs self-start">
        {(Object.keys(SOURCE_LABELS) as AllocSource[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSource(s)}
            className={`rounded-tile px-3 py-1.5 ${source === s ? 'bg-sf-accent text-sf-ink' : 'text-sf-ink-3'}`}
          >
            {SOURCE_LABELS[s]}
          </button>
        ))}
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && data.status !== 'ok'}
        emptyLabel="仓位落地暂不可用"
        emptyHint="市场仓位或评分源不可得（后端诚实降级，不臆算）"
      >
        {data && data.status === 'ok' ? <AllocationBody data={data} /> : null}
      </QueryState>
    </div>
  )
}

function AllocationBody({ data }: { data: PositionAllocation }) {
  const meta = data.meta ?? {}
  const mkt = (meta.market ?? {}) as Record<string, unknown>
  const src = (meta.source ?? {}) as Record<string, unknown>
  const allocations = data.allocations ?? []
  const excluded = data.excluded ?? []
  const capped = meta.capped ?? []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <Stat label="市场温度" value={typeof mkt.temperature === 'number' ? f2(mkt.temperature) : '—'} />
        <Stat label="目标总敞口" value={pct(meta.target_pct)} />
        <Stat label="Σ目标权重" value={pct(meta.sum_pct)} />
        <Stat label="单票上限" value={pct(meta.cap_pct)} />
        <Stat label="分配票数" value={f2(meta.n_alloc)} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat label="快照数据日" value={typeof mkt.snapshot_date === 'string' ? String(mkt.snapshot_date) : '—'} />
        <Stat label="仓位档" value={typeof mkt.band === 'string' ? String(mkt.band) : '—'} />
        <Stat label="剔除票数（评分缺失）" value={f2(meta.n_excluded)} />
      </div>

      {meta.degraded ? (
        <div className="rounded-tile bg-sf-surface-2 px-3 py-2 text-xs text-sf-ink-3">
          ℹ️ 等权明示降级：未使用任何评分信号（标的池无逐票评分可用），权重仅为均分参考，不构成强弱排序。
        </div>
      ) : null}

      {typeof meta.overflow_pct === 'number' && meta.overflow_pct > 0 ? (
        <div className="rounded-tile bg-sf-surface-2 px-3 py-2 text-xs text-sf-ink-3">
          ⚠️ 标的数 × 单票上限不足以承载市场仓位：总敞口被封顶在 {pct(meta.sum_pct)}（目标 {pct(meta.target_pct)}，
          缺口 {pct(meta.overflow_pct)} 如实少配，不凑满）。
        </div>
      ) : null}

      {capped.length > 0 ? (
        <div className="text-xs text-sf-ink-3">
          截断标注：{capped.join('、')} 触及单票上限，超出部分已按权重重分给其余标的。
        </div>
      ) : null}

      <Card title={`目标权重分配（${allocations.length} 只）`}>
        {allocations.length === 0 ? (
          <div className="text-xs text-sf-ink-3">暂无分配结果。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-sf-ink">
              <thead>
                <tr className="text-sf-ink-3 border-b border-sf-line">
                  <th className="text-left py-1.5 pr-3">代码</th>
                  <th className="text-left py-1.5 pr-3">名称</th>
                  <th className="text-right py-1.5 pr-3">评分</th>
                  <th className="text-right py-1.5 pr-3">目标权重</th>
                  <th className="text-right py-1.5 pr-3">目标仓位%</th>
                  <th className="text-left py-1.5">触上限</th>
                </tr>
              </thead>
              <tbody>
                {allocations.map((a, i) => (
                  <tr key={`${a.code}-${i}`} className="border-b border-sf-line/60">
                    <td className="py-1.5 pr-3">{a.code}</td>
                    <td className="py-1.5 pr-3">{a.name ?? '—'}</td>
                    <td className="py-1.5 pr-3 text-right">{a.score == null ? '—' : f2(a.score)}</td>
                    <td className="py-1.5 pr-3 text-right">{a.weight == null ? '—' : `${(a.weight * 100).toFixed(2)}%`}</td>
                    <td className="py-1.5 pr-3 text-right">{a.pct == null ? '—' : pct(a.pct)}</td>
                    <td className="py-1.5">{capped.includes(a.code) ? '是' : '否'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {excluded.length > 0 ? (
        <Card title={`被剔除标的（${excluded.length}，评分缺失不编造）`}>
          <ul className="text-xs text-sf-ink-3 space-y-1">
            {excluded.map((e, i) => (
              <li key={`${e.code}-${i}`}>
                <span className="text-sf-ink">{e.code}</span> {e.name ?? ''}：{e.reason ?? '评分缺失'}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <div className="text-xs text-sf-ink-3">
        评分源：{SOURCE_LABELS[(data.source as AllocSource) ?? 'recommend']}
        {typeof src.generated_at === 'string' ? `　｜　推荐生成 ${src.generated_at}` : ''}
        {typeof src.data_as_of === 'string' ? `　｜　行情截至 ${src.data_as_of}` : ''}
        {typeof mkt.snapshot_date === 'string' ? `　｜　市场快照 ${mkt.snapshot_date}` : ''}
        ，建议 ≠ 交易，请结合自身风控独立决策。
      </div>

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}
