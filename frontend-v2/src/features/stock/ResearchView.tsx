import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import type { EChartsOption } from 'echarts'
import type { StockKline, ResearchDeep, SixDim, StockProfile, TechnicalScore, DimKey } from '@/api/schemas/stock'
import { DIM_KEYS } from '@/api/schemas/stock'
import type { ResearchView as ViewMode, ResearchRouteSearch } from '@/lib/deeplink'
import { useStockIntraday, useStockKline, useSixDim, useStockProfile, useTechnicalScore } from '@/lib/queries'
import { getResearchDeep } from '@/api/stock'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { Stat } from '@/shared/ui/Stat'
import { CollapsibleCard } from '@/shared/ui/CollapsibleCard'
import { ScoreBar } from '@/shared/ui/ScoreBar'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { inkForCell } from '@/lib/domainColor'
import { fmtNum } from '@/lib/format'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'
import { KLineChart } from './charts/KLineChart'
import { IntradayChart } from './charts/IntradayChart'
import { submitAnalysisTask, useCompositeTask } from './scoreTask'

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
  // 选中项名称（来自搜索结果 item），仅用于回显；未匹配到名称（直接按代码查询）时如实只显代码。
  const [codeName, setCodeName] = useState<string | null>(null)

  const valid = CODE_RE.test(input)
  const kline = useStockKline(input)
  // 反向出边携带当前有效代码（非法输入时回落到初始预选值），不把非法 code 写进 URL。
  const linkCode = valid ? input : initialCode

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <SectionTitle as="h2">个股研究</SectionTitle>
        <span className="text-label text-sf-ink-3">数据源 stock-kline</span>
        <Link
          to="/stock/fundamentals"
          search={{ code: linkCode }}
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          {`← 返回基本面分析（${linkCode}）`}
        </Link>
      </div>

      {/* 股票名称+简介信息卡：页面顶部，代码输入区上方；code 变更即随当前有效代码刷新。 */}
      <ProfileCard code={linkCode} />

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

      {/* 代码输入：统一 StockSearchInput（代码/名称/拼音召回）。选中后回写并回显
          name(code)；未匹配到名称时如实只显代码。非法码不发请求（useStockKline enabled=false）。 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-72">
          <StockSearchInput
            value={input}
            label="搜索股票（代码 / 名称 / 首字母）"
            onSelect={(code, item) => {
              setInput(code)
              setCodeName(item?.name ?? null)
            }}
          />
        </div>
        <span className="text-label text-sf-ink-3">
          {`当前标的：${codeName ? `${codeName}（${linkCode}）` : linkCode}`}
        </span>
      </div>

      {view === 'quick' ? (
        <QuickView kline={kline} valid={valid} code={input} />
      ) : (
        <DeepView code={linkCode} />
      )}
    </div>
  )
}

/** chip 样式（代码/行业/板块共用）：低强调圆角胶囊。 */
const CHIP = 'rounded-full border border-sf-line px-2 py-0.5 text-label text-sf-ink-2'

/**
 * 股票名称+简介信息卡（GET /api/v2/read/stock-profile）。
 * 诚实红线：name/industry/board/core_business/price/market_cap 逐字段独立降级，
 * null 如实展示（core_business null → 「暂无简介（同花顺源不可用）」，不拿行业顶替、不编造）；
 * date 生产恒 null（get_fundamentals 无数据日字段）→ 「暂无权威数据日」，禁当前日期兜底。
 */
function ProfileCard({ code }: { code: string }) {
  const q = useStockProfile(code)
  return (
    <Card title="股票信息">
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={false}>
        {q.data ? <ProfileBody d={q.data} /> : null}
      </QueryState>
    </Card>
  )
}

function ProfileBody({ d }: { d: StockProfile }) {
  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-page font-semibold text-sf-ink">{d.name ?? '—'}</span>
        <span className={`${CHIP} tabular-nums`}>{d.code}</span>
        {d.industry !== null && <span className={CHIP}>{d.industry}</span>}
        {d.board !== null && <span className={CHIP}>{d.board}</span>}
      </div>
      {d.core_business === null ? (
        <p className="text-label text-sf-ink-3">暂无简介（同花顺源不可用）</p>
      ) : (
        <p className="text-body text-sf-ink-2">{d.core_business}</p>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Stat label="最新价" value={d.price === null ? '—' : fmtNum(d.price)} />
        <Stat label="总市值（亿）" value={d.market_cap === null ? '—' : fmtNum(d.market_cap)} />
      </div>
      {d.date === null ? (
        <p role="status" className="text-label text-sf-warn">暂无权威数据日</p>
      ) : (
        <p className="text-label text-sf-ink-3">{`权威数据日：${d.date}`}</p>
      )}
      <p className="text-label text-sf-ink-3">{d.note}</p>
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
  // 折叠卡摘要：最新收盘（rows[0]，后端日线按新→旧排列）/ 权威数据日 / 根数；缺失如实「—」。
  const rows = kline.data?.rows ?? []
  const lastClose = rows.length > 0 && typeof rows[0]?.close === 'number' ? fmtNum(rows[0].close) : '—'
  const dateTxt =
    kline.data === undefined ? '—' : kline.data.date === null ? '暂无权威数据日' : kline.data.date
  const tableSummary = `最新收盘 ${lastClose} · 权威数据日 ${dateTxt} · ${rows.length} 根`
  return (
    <>
      <Card title="K 线图表（daily）">
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
          /* 超长 OHLC 表折叠：折叠态只留摘要行，children（整张表）不渲染；
             加载/错误/空态仍在折叠卡之外独立可见，不被折叠藏住。 */
          <CollapsibleCard
            title="K 线 OHLC 数据表（daily）"
            summary={tableSummary}
            defaultOpen={false}
          >
            <KlineTable rows={kline.data.rows} />
          </CollapsibleCard>
        ) : null}
      </QueryState>
      {/* note 为后端原文，原样展示。 */}
      {kline.data && kline.data.note !== null && (
        <p className="text-body text-sf-ink-2 mt-3">{kline.data.note}</p>
      )}
    </Card>
      {/* 多维度评分区：技术面打分 + 六维评分 + 五维综合（异步任务）。 */}
      <ScoreZone code={code} />
    </>
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

// ═══════════ 多维度评分区（quick 视图 · K 线卡下方）═══════════
// 三块数据源各自独立：technical-score（只读端点）/ six-dim（复用 useSixDim）/
// 五维综合（analysis 异步任务，scoreTask.ts 模块级轮询）。
// 诚实红线：SignalEngine 信号评分 / 事件评分 / 宏观板块评分是重型多源独立系统（未 API 化），
// 本区不做也不伪造，仅在底部低强说明可走 /legacy。

/** 六维中文标签（顺序与 DIM_KEYS 一致；与 SixDimView 同源副本，避免跨文件耦合）。 */
const SIX_DIM_LABELS: Record<DimKey, string> = {
  technical: '技术',
  capital: '资金',
  value: '价值',
  growth: '成长',
  fundamental: '基本面',
  cycle: '周期',
}

/** 六维雷达 option（自 SixDimView 复制的本地渲染；缺失维以 null 不绘制，不补 0）。 */
function sixDimRadarOption(d: SixDim): EChartsOption {
  const radarValues: (number | null)[] = DIM_KEYS.map((k) =>
    typeof d.dims[k] === 'number' ? d.dims[k] : null,
  )
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    radar: {
      indicator: DIM_KEYS.map((k) => ({ name: SIX_DIM_LABELS[k], max: 100 })),
      axisName: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
      splitLine: { lineStyle: { color: CHART.line } },
      splitArea: { show: false },
    },
    series: [
      {
        type: 'radar',
        symbolSize: 5,
        data: [
          {
            value: radarValues,
            name: '六维评分',
            itemStyle: { color: CHART.accent },
            lineStyle: { color: CHART.accent, width: 1.5 },
            areaStyle: { color: CHART.accent, opacity: 0.15 },
          },
        ],
      },
    ],
  }
}

function ScoreZone({ code }: { code: string }) {
  return (
    <Card title="多维度评分">
      <div className="flow">
        <TechnicalScoreSection code={code} />
        <SixDimSection code={code} />
        <CompositeSection code={code} />
        {/* 诚实说明：以下三类评分为重型异步引擎能力，v2 未 API 化，不伪造。 */}
        <p className="text-label text-sf-ink-3">
          信号/事件/宏观板块评分依赖重型异步引擎，可走 /legacy 查看旧版
        </p>
      </div>
    </Card>
  )
}

/**
 * 技术面评分（GET /api/v2/read/technical-score）：
 * ScoreBar×5（趋势/动量/量能/技术综合 + 多周期综合）+ short/mid/long 三个 Stat。
 * technical=null（三维全失败/无有效K线）→ 诚实显示 note 降级说明，绝不补 0/50；
 * patterns 空数组 → 「无形态信号」；overall 缺维按底层算法当中性 50 参与（后端语义）。
 */
function TechnicalScoreSection({ code }: { code: string }) {
  const q = useTechnicalScore(code)
  return (
    <section className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
      <h4 className="text-body font-semibold text-sf-ink mb-2">技术面评分</h4>
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={false}>
        {q.data ? <TechScoreBody d={q.data} /> : null}
      </QueryState>
    </section>
  )
}

function TechScoreBody({ d }: { d: TechnicalScore }) {
  // 整块降级：technical=null → note 里已注明「technical=null，不补值」，原文展示。
  if (d.technical === null) {
    return <p role="status" className="text-body text-sf-ink-2">{d.note}</p>
  }
  const t = d.technical
  const p = d.periods
  return (
    <div className="flow">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <ScoreBar label="趋势" value={t.trend} />
        <ScoreBar label="动量" value={t.momentum} />
        <ScoreBar label="量能" value={t.volume} />
        <ScoreBar label="技术综合" value={t.overall} />
        {/* periods 整块 null → 多周期综合按缺失「—」 */}
        <ScoreBar label="多周期综合" value={p === null ? null : p.composite} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="短期" value={p === null || p.short === null ? '—' : fmtNum(p.short)} />
        <Stat label="中期" value={p === null || p.mid === null ? '—' : fmtNum(p.mid)} />
        <Stat label="长期" value={p === null || p.long === null ? '—' : fmtNum(p.long)} />
      </div>
      {t.patterns.length === 0 ? (
        <p className="text-label text-sf-ink-3">无形态信号</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {t.patterns.map((pat) => (
            <span key={pat} className={CHIP}>{pat}</span>
          ))}
        </div>
      )}
      {d.date === null ? (
        <p role="status" className="text-label text-sf-warn">暂无权威数据日</p>
      ) : (
        <p className="text-label text-sf-ink-3">{`权威数据日：${d.date}`}</p>
      )}
      <p className="text-label text-sf-ink-3">{d.note}</p>
    </div>
  )
}

/**
 * 六维评分嵌入（复用 useSixDim）：雷达 option 本地渲染 + 6 条 ScoreBar；
 * coverage<6 显式告知「仅 X/6 维有效」；链接到 /stock/six-dim 完整页。
 */
function SixDimSection({ code }: { code: string }) {
  const q = useSixDim(code)
  return (
    <section className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
      <div className="flex items-center justify-between gap-3 mb-2">
        <h4 className="text-body font-semibold text-sf-ink">六维评分</h4>
        <Link
          to="/stock/six-dim"
          className="text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          六维评分完整页 →
        </Link>
      </div>
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={false}>
        {q.data ? <SixDimMiniBody d={q.data} /> : null}
      </QueryState>
    </section>
  )
}

function SixDimMiniBody({ d }: { d: SixDim }) {
  return (
    <div className="flow">
      {d.coverage < 6 && (
        <div role="status" className="text-body text-sf-ink-2">
          {`仅 ${d.coverage}/6 维有效，缺失维未取到数据`}
        </div>
      )}
      <EChart
        option={sixDimRadarOption(d)}
        height={260}
        ariaLabel="个股六维评分雷达图（缩略）：缺失维度不绘制数据点"
      />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {DIM_KEYS.map((k) => (
          <ScoreBar key={k} label={SIX_DIM_LABELS[k]} value={d.dims[k]} />
        ))}
      </div>
    </div>
  )
}

// ───────── 五维综合（analysis 异步任务，scoreTask.ts 模块级轮询）─────────

/** 评分环配色（评分语义，非价格涨跌语义，用状态令牌色）：≥70 红 / ≤40 绿 / 中间琥珀。 */
function verdictColor(composite: number): string {
  if (composite >= 70) return 'var(--color-sf-danger)'
  if (composite <= 40) return 'var(--color-sf-ok)'
  return 'var(--color-sf-warn)'
}

/** verdict 文案：后端给了就用原文；缺 verdict 时按同一阈值派生展示语义（≥70 看多 / ≤40 看空 / 观望）。 */
function verdictText(r: { verdict: string | null | undefined; composite: number }): string {
  if (r.verdict) return r.verdict
  if (r.composite >= 70) return '看多'
  if (r.composite <= 40) return '看空'
  return '观望'
}

/** SVG 评分环（v1 _score_ring_html 概念迁移）：圆环按分值比例填充，中心数字。 */
function ScoreRing({ score, color }: { score: number; color: string }) {
  const pct = Math.min(100, Math.max(0, score))
  const r = 54
  const c = 2 * Math.PI * r
  const dash = (c * pct) / 100
  return (
    <svg
      width="140"
      height="140"
      viewBox="0 0 140 140"
      role="img"
      aria-label={`五维综合评分：${pct}`}
    >
      <circle cx="70" cy="70" r={r} fill="none" stroke="var(--color-sf-line)" strokeWidth="12" />
      <circle
        cx="70"
        cy="70"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="12"
        strokeLinecap="round"
        strokeDasharray={`${dash.toFixed(1)} ${c.toFixed(1)}`}
        transform="rotate(-90 70 70)"
      />
      <text x="70" y="80" textAnchor="middle" fontSize="34" fontWeight="700" fill={color}>
        {pct}
      </text>
    </svg>
  )
}

/**
 * 五维综合评分块：默认 idle 只显示按钮（不自动发起）；提交/轮询态显示阶段与用时；
 * 完成 → 评分环 + verdict 徽标 + 5 条子分 ScoreBar；失败/超时诚实中文提示，不造假分。
 * 任务态存于模块级 store（scoreTask.ts）：切页不打断轮询，同会话切回来结果还在。
 */
function CompositeSection({ code }: { code: string }) {
  const st = useCompositeTask(code)

  if (st.phase === 'idle') {
    return (
      <section className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
        <h4 className="text-body font-semibold text-sf-ink mb-2">五维综合评分</h4>
        <button
          type="button"
          onClick={() => submitAnalysisTask(code)}
          className="rounded-tile border border-sf-line bg-sf-surface px-4 py-2 text-body text-sf-ink hover:border-sf-accent hover:text-sf-accent"
        >
          生成五维综合评分（异步约 10-30 秒）
        </button>
        <p className="text-label text-sf-ink-3 mt-2">
          提交后由后台 analysis 引擎异步计算（技术/新闻/宏观/量能/板块五维合成），本页不自动发起。
        </p>
      </section>
    )
  }

  if (st.phase === 'submitting' || st.phase === 'polling') {
    return (
      <section className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
        <h4 className="text-body font-semibold text-sf-ink mb-2">五维综合评分</h4>
        <div role="status" className="text-body text-sf-ink-2">
          {st.phase === 'submitting' ? '任务提交中…' : '后台计算中…'}
          {st.stage !== null && <span>{`（${st.stage}）`}</span>}
          {st.elapsedS !== null && (
            <span className="text-label text-sf-ink-3">{` 已用时 ${st.elapsedS}s`}</span>
          )}
        </div>
      </section>
    )
  }

  if (st.phase === 'error') {
    return (
      <section className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
        <h4 className="text-body font-semibold text-sf-ink mb-2">五维综合评分</h4>
        <div role="alert" className="text-body text-sf-warn">
          {`五维综合评分失败：${st.error ?? '未知错误'}`}
        </div>
        <button
          type="button"
          onClick={() => submitAnalysisTask(code)}
          className="mt-2 rounded-tile border border-sf-line bg-sf-surface px-4 py-2 text-body text-sf-ink hover:border-sf-accent hover:text-sf-accent"
        >
          重试
        </button>
      </section>
    )
  }

  // done：综合分缺失 → 诚实告知，不画 0 分环
  const r = st.result
  const composite = r && typeof r.composite === 'number' ? r.composite : null
  if (r === null || composite === null) {
    return (
      <section className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
        <h4 className="text-body font-semibold text-sf-ink mb-2">五维综合评分</h4>
        <div role="status" className="text-body text-sf-ink-2">
          {`任务完成但后端未返回综合评分（composite 缺失），`}
          <LeadText>如实展示，不伪造分数</LeadText>
          {`。`}
        </div>
      </section>
    )
  }
  const color = verdictColor(composite)
  return (
    <section className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
      <h4 className="text-body font-semibold text-sf-ink mb-2">五维综合评分</h4>
      <div className="flex flex-wrap items-center gap-4">
        <ScoreRing score={composite} color={color} />
        <span
          className="rounded-full border px-3 py-1 text-body font-semibold"
          style={{ color, borderColor: color }}
        >
          {verdictText({ verdict: r.verdict, composite })}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <ScoreBar label="技术分" value={r.tech_score ?? null} color={color} />
        <ScoreBar label="新闻情绪分" value={r.news_score ?? null} color={color} />
        <ScoreBar label="宏观分" value={r.macro_score ?? null} color={color} />
        <ScoreBar label="量能分" value={r.vol_score ?? null} color={color} />
        <ScoreBar label="板块分" value={r.sector_score ?? null} color={color} />
      </div>
    </section>
  )
}

/**
 * deep 子视图（W4-C 迁移后真实内容）：调 getResearchDeep（/v2/read/research-deep，
 * 56 键深度分析通用透传），渲染 price/pe_ttm/pb/market_cap/ma5/ma10/ma20/ma60/
 * amplitude/turnover 等技术字段表，按 domainInk 域级双色。
 *
 * 诚实豁免：若返回 deep_analysis_available === false（或该字段缺失且无任何技术字段），
 * 在真实技术字段表之后追加明确说明「56 键深度分析（旧版 analysis_engine 异步任务）V2
 * 暂未接入，可走 /legacy 查看旧版」——说明不替换、不短路已返回的真实字段；绝不造假数据、
 * 不画空图表。
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

export function DeepBody({ data }: { data: ResearchDeep }) {
  const techKeys = Object.keys(data).filter((k) => !DEEP_META.has(k))
  const hasTech = techKeys.length > 0
  // 豁免：明确 false，或字段缺失且无任何技术字段（无法确认已接入）。
  const exempt = isDeepExempt(data)

  // 无真实字段且非豁免态：如实空态，不补零、不编造。
  if (!hasTech && !exempt) {
    return (
      <div role="status" className="py-10 text-center text-body text-sf-ink-2">
        暂无深度数据
      </div>
    )
  }

  return (
    <div className="flow">
      {/* 真实字段表：有技术字段就照后端原始 key 渲染（域级双色），豁免态不再短路隐藏。
          表包折叠卡（默认展开，保持 DeepExemptRendering 守卫「不点击即可见」语义）：
          summary 给 price/pe_ttm/ma5 摘要，null 用「—」。 */}
      {hasTech && (
        <CollapsibleCard
          title="深度技术字段"
          summary={(() => {
            const rec = data as Record<string, unknown>
            const cell = (k: string) => (typeof rec[k] === 'number' ? fmtNum(rec[k]) : '—')
            return `price ${cell('price')} · pe_ttm ${cell('pe_ttm')} · ma5 ${cell('ma5')}`
          })()}
          defaultOpen={true}
        >
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
        </CollapsibleCard>
      )}
      {/* 诚实说明：56 键异步深度分析未接入时追加在真实字段表之后（低强调），
          不替换、不短路已有的真实技术字段。 */}
      {exempt && (
        <div className="mt-3">
          <p className="text-label text-sf-ink-3">
            56 键深度分析（旧版 analysis_engine 异步任务）V2 暂未接入，可走 /legacy 查看旧版
          </p>
          <p className="text-label text-sf-ink-3">{`已预选 code：${String(data['code'] ?? '')}`}</p>
        </div>
      )}
    </div>
  )
}
