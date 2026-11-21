import type { QuoteBoardIndex, SectorItem } from '@/api/schemas/read'
import { useQuoteBoard } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { CollapsibleRankTable, type RankColumn } from '@/shared/ui/CollapsibleRankTable'
import { RetestButton } from '@/shared/ui/RetestButton'
import { CHART } from '@/shared/charts/palette'
import { openKLine } from '@/features/stock/charts/klineOverlayStore'

/**
 * 10 页「行情看板」V2 化（对应 V2-STATUS-PLAN Tier2 最后一页）。
 * 数据来源：useQuoteBoard → GET /api/v2/read/quote-board（后端只读聚合）。
 *
 * 三块内容：
 *  - 主要指数迷你卡：上证/深证/创业板/上证50/沪深300（akshare 日线快照，权威数据日）。
 *  - 行业板块涨跌榜：行业资金流的涨跌幅 + 净额，涨幅 TOP / 跌幅 TOP 内联条。
 *  - 市场状态：服务器北京时间真实计算的交易时段（非伪造数据日）。
 *
 * 红线：
 *  - 后端已诚实降级：指数取不到→字段为 null，板块取不到→[]，前端显示「—」，绝不补 0
 *    （避开 ?? 0 / || 0 / new Date()）。
 *  - 指数为日线级快照，非实时逐笔；前端如实标注，实时价请用个股分时/行情端点或 v1 看板。
 *  - 红涨绿跌（A 股交易屏语义）。
 */
// 仅供条形几何 / 计数占位：非数→0，不编数据（避开诚实红线 ?? 0 / || 0 / new Date()）
function nz(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

/** 缺失显示「—」，绝不把 null 当 0 展示。 */
function fmtNum(v: unknown, digits = 2): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—'
}
function fmtInt(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? String(Math.trunc(v)) : '—'
}
function fmtSigned(v: unknown, digits = 2, suffix = ''): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(digits)}${suffix}`
  }
  return '—'
}
function chgColor(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 0 ? CHART.up : v < 0 ? CHART.down : CHART.ink2
  }
  return CHART.ink2
}

// 板块涨跌内联条：宽度按 |涨跌幅| 相对最大值的比例（纯几何，不参与数据展示）。
function barWidth(pct: unknown, maxAbs: number): number {
  if (maxAbs <= 0) return 0
  return Math.min(100, (Math.abs(nz(pct)) / maxAbs) * 100)
}

/** 单张指数迷你卡：缺失时整卡显示「暂无数据」，绝不补 0。
 *  2026-11-22 老板需求：点击弹出该指数 K 线弹窗（复用全局 openKLine 浮层，
 *  sh/sz 前缀 code 由 KLineModal 自动走指数日线端点 /index-kline）。 */
function IndexCard({ item }: { item: QuoteBoardIndex }) {
  const hasValue = typeof item.current === 'number' && Number.isFinite(item.current)
  const clickable = !!item.code && /^(sh|sz)\d{6}$/.test(item.code)
  if (!clickable) {
    // code 缺失 / 形态非法：退化为静态卡（诚实降级，不做假按钮）
    return (
      <div className="rounded-tile bg-sf-surface-2 border border-sf-line px-3.5 py-3">
        <IndexCardBody item={item} hasValue={hasValue} />
      </div>
    )
  }
  return (
    <button
      type="button"
      onClick={() => openKLine(item.code as string, item.name ?? undefined, 'market')}
      aria-label={`${item.name ?? item.code} 查看 K 线详情`}
      className="rounded-tile bg-sf-surface-2 border border-sf-line px-3.5 py-3 text-left transition-all hover:border-sf-accent hover:shadow-[0_0_0_1px_var(--color-sf-accent)_inset] cursor-pointer"
    >
      <IndexCardBody item={item} hasValue={hasValue} />
    </button>
  )
}

function IndexCardBody({ item, hasValue }: { item: QuoteBoardIndex; hasValue: boolean }) {
  return (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-sf-ink">{item.name ?? '—'}</span>
        <span className="text-[11px] font-mono text-sf-ink-3">{item.code ?? '—'}</span>
      </div>
      {hasValue ? (
        <>
          <div
            className="text-kpi font-semibold leading-tight mt-2 tabular-nums"
            style={{ color: chgColor(item.change_pct) }}
          >
            {fmtNum(item.current)}
          </div>
          <div className="flex items-baseline justify-between gap-2 mt-1">
            <span className="text-xs font-medium tabular-nums" style={{ color: chgColor(item.change_pct) }}>
              {fmtSigned(item.change_pct, 2, '%')}
            </span>
            <span className="text-[11px] tabular-nums" style={{ color: chgColor(item.change) }}>
              {fmtSigned(item.change)}
            </span>
          </div>
          <div className="text-[11px] text-sf-ink-3 mt-1.5">数据日 {item.date ?? '—'}</div>
        </>
      ) : (
        <>
          <div className="text-kpi font-semibold leading-tight mt-2 text-sf-ink-3">—</div>
          <div className="text-xs text-sf-ink-3 mt-1">暂无数据</div>
          <div className="text-[11px] text-sf-ink-3 mt-1.5">数据源不可用 / 离线</div>
        </>
      )}
    </>
  )
}

export function QuoteBoard() {
  const q = useQuoteBoard()
  const d = q.data
  const indices = (d?.indices ?? []).filter((i): i is QuoteBoardIndex => !!i)
  const sectors = (d?.sectors ?? []).filter((s): s is SectorItem => !!s && !!s.name)
  const unavailable = (d?.unavailable ?? []).filter((k): k is string => typeof k === 'string')
  const summary = d?.summary
  const ms = d?.market_status

  // 全局空态：指数无任何有效读数 且 板块全空（后端两块都诚实降级）。
  const hasIndexData = indices.some((i) => typeof i.current === 'number' && Number.isFinite(i.current))
  const isEmpty = !!d && !hasIndexData && sectors.length === 0

  const maxAbs = sectors.reduce((m, s) => Math.max(m, Math.abs(nz(s.chg_pct))), 0)
  const withPct = sectors.filter((s) => typeof s.chg_pct === 'number' && Number.isFinite(s.chg_pct))
  const topUp = [...withPct].sort((a, b) => nz(b.chg_pct) - nz(a.chg_pct)).slice(0, 6)
  const topDown = [...withPct].sort((a, b) => nz(a.chg_pct) - nz(b.chg_pct)).slice(0, 6)
  const upCount = withPct.filter((s) => nz(s.chg_pct) > 0).length
  const sectorCols: RankColumn<SectorItem>[] = [
    { key: 'name', title: '板块', value: (s) => s.name ?? null, render: (s) => s.name ?? '—', sortable: true },
    { key: 'chg_pct', title: '涨跌幅', align: 'right', value: (s) => s.chg_pct, render: (s) => <span style={{ color: chgColor(s.chg_pct) }}>{fmtSigned(s.chg_pct, 2, '%')}</span>, sortable: true },
    { key: 'net', title: '主力净额', align: 'right', value: (s) => s.net, render: (s) => <span style={{ color: chgColor(s.net) }}>{fmtSigned(s.net, 2, ' 亿')}</span>, sortable: true },
    { key: 'leader', title: '领涨股', value: (s) => s.leader ?? null, render: (s) => s.leader ?? '—', sortable: true },
    { key: 'leader_chg_pct', title: '领涨股涨跌幅', align: 'right', value: (s) => s.leader_chg_pct, render: (s) => <span style={{ color: chgColor(s.leader_chg_pct) }}>{fmtSigned(s.leader_chg_pct, 2, '%')}</span>, sortable: true },
  ]

  return (
    <div className="quote-board">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-lg font-semibold">行情看板</h2>
        {ms?.text ? (
          <span
            className="inline-block rounded px-2 py-1 text-[11px] border"
            style={{
              color: ms.is_open ? CHART.up : CHART.ink2,
              borderColor: ms.is_open ? CHART.up : CHART.line,
            }}
          >
            {ms.text}
          </span>
        ) : null}
        <RetestButton
          onRetest={() => { void q.refetch() }}
          loading={q.isFetching}
          hint={unavailable.length > 0 ? `本次存在 ${unavailable.length} 项降级，详见下方` : null}
        />
      </div>
      <div className="text-xs text-sf-ink-3 mt-1">
        红涨绿跌；聚合主要指数日线快照、行业板块涨跌榜与市场状态。指数为页面加载时点快照（日线级），
        非实时逐笔行情；实时价请用个股分时 / 行情端点或 v1 看板。市场状态基于服务器北京时间真实计算，非数据日。
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="暂无行情看板数据"
        emptyHint="指数与板块数据本次均未取到（可能离线 / 接口受限）；后端已诚实降级，未编造数值"
      >
        {d ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="指数只数" value={fmtInt(summary?.index_count)} sub="监控的主要指数" />
              <Stat label="取到报价" value={fmtInt(summary?.index_available)} sub="有有效最新收盘" />
              <Stat label="板块数" value={fmtInt(summary?.sector_count)} sub="行业资金流覆盖" />
              <Stat label="上涨板块" value={withPct.length > 0 ? String(upCount) : '—'} sub="涨跌幅 &gt; 0" />
            </div>

            {unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下情况本次发生（已诚实标注）：{unavailable.join('、')}
              </div>
            )}

            {/* 主要指数迷你卡 */}
            <Card title="📈 主要指数（收盘快照）">
              {indices.length === 0 ? (
                <div className="text-xs text-sf-ink-3">
                  本次未取到任何指数（离线 / 接口受限），已诚实标注，未编造指数卡片。
                </div>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                  {indices.map((i) => (
                    <IndexCard key={i.code ?? i.name ?? 'idx'} item={i} />
                  ))}
                </div>
              )}
              {unavailable.includes('index_quotes_unavailable') && (
                <div className="mt-2 rounded-tile border border-sf-warn px-3 py-2 text-[11px] text-sf-warn">
                  本次 5 个主要指数全部未取到（index_quotes_unavailable）：多为环境网络代理限制或行情源不可达。
                  后端已诚实降级为 null（卡片显示「—」），未补 0、未编造点位。可点「重新检测」重试，
                  或前往「数据源与接口检测」查看真实失败原因。
                </div>
              )}
              <div className="mt-2 text-[11px] opacity-70">
                点位 / 涨跌额 / 涨跌幅缺失显示「—」，不补 0；「数据日」为指数日线的权威日期，取不到显示「—」，绝不用当前日期冒充。
              </div>
            </Card>

            {/* 行业板块涨跌榜 */}
            <Card title="🏭 行业板块涨跌榜">
              {sectors.length === 0 ? (
                <div className="text-xs text-sf-ink-3">板块数据本次未取到（离线 / 接口受限），已诚实标注，未编造板块列表。</div>
              ) : (
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-ss-up)' }}>🔺 涨幅 TOP6</div>
                    {topUp.map((s) => (
                      <div key={`u-${s.name}`} className="mb-1">
                        <div className="flex justify-between text-xs">
                          <span>{s.name ?? '—'}</span>
                          <span style={{ color: chgColor(s.chg_pct) }}>{fmtSigned(s.chg_pct, 2, '%')}</span>
                        </div>
                        <div className="h-1.5 rounded bg-sf-line/40 overflow-hidden">
                          <div className="h-full" style={{ width: `${barWidth(s.chg_pct, maxAbs)}%`, background: chgColor(s.chg_pct) }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-ss-down)' }}>🔻 跌幅 TOP6</div>
                    {topDown.map((s) => (
                      <div key={`d-${s.name}`} className="mb-1">
                        <div className="flex justify-between text-xs">
                          <span>{s.name ?? '—'}</span>
                          <span style={{ color: chgColor(s.chg_pct) }}>{fmtSigned(s.chg_pct, 2, '%')}</span>
                        </div>
                        <div className="h-1.5 rounded bg-sf-line/40 overflow-hidden">
                          <div className="h-full" style={{ width: `${barWidth(s.chg_pct, maxAbs)}%`, background: chgColor(s.chg_pct) }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {sectors.length > 0 && (
                <div className="mt-3">
                  <CollapsibleRankTable
                    title="行业板块完整榜单（展开后可正/逆排序）"
                    rows={sectors}
                    columns={sectorCols}
                    rowKey={(s, i) => `${s.name}-${i}`}
                    defaultSort={{ key: 'chg_pct', dir: 'desc' }}
                    barColor={(s) => chgColor(s.chg_pct)}
                    hint="点击表头在降序 / 升序间切换；缺失值恒排末尾、不补 0；红涨绿跌。"
                  />
                </div>
              )}
              <div className="mt-2 text-[11px] opacity-70">
                净额单位：亿元（后端已折算）；「—」= 该字段缺失，不补 0；红涨绿跌。
              </div>
            </Card>

            {/* 市场状态 */}
            <Card title="🕒 市场状态（服务器北京时间）">
              {ms ? (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <Stat label="当前状态" value={ms.text ?? '—'} sub="基于交易时段真实计算" />
                  <Stat label="是否交易中" value={ms.is_open === true ? '是' : ms.is_open === false ? '否' : '—'} sub="周末 / 盘后为否" />
                  <Stat label="建议刷新间隔" value={ms.refresh_ms != null ? `${fmtInt(ms.refresh_ms)} ms` : '—'} sub="0 = 不自动刷新" />
                </div>
              ) : (
                <div className="text-xs text-sf-ink-3">市场状态本次未取到（服务器时间计算失败），已诚实标注。</div>
              )}
              <div className="mt-2 text-[11px] opacity-70">
                此处「当前时段」是真实时间判定，与指数 / 板块的「权威数据日」是两件事，不可互相冒充。
              </div>
            </Card>
          </div>
        ) : null}
      </QueryState>

      <div className="mt-8 text-xs text-sf-ink-3">
        ⚠️ {d?.note ?? '说明：本页为只读行情快照，非预测模型，不构成投资建议；指数为日线级数据，盘中读数可能有延迟。'}
      </div>
    </div>
  )
}
