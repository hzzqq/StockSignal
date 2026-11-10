import { useEffect, useMemo, useState, type ReactNode, type ReactElement } from 'react'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { fmtNum } from '@/lib/format'
import {
  useDailySnapshot,
  useDailyRecommendation,
  useBreadthTimeseries,
  useEventPool,
  useBacktestRuns,
} from '@/lib/queries'
import type {
  DailySnapshot,
  DailyRecommendation,
  BreadthPoint,
  EventPool,
  BacktestRuns,
} from '@/api/schemas/read'

/**
 * 73 自定义看板（/dashboard-custom，v2 native）。
 *
 * 聚合现有只读端点，做成可由用户勾选的组件看板；选择持久化在 localStorage（不依赖服务端
 * 写入），刷新后保留。每个组件都是真实只读端点 + 诚实渲染（null 显「—」、收益为负如实红绿、
 * 不回测美化、不编造列表）。
 *
 * ⚠️ 诚实红线：本页不引入任何「合成」数据；组件清单固定为 5 个真实端点，缺失字段一律显「—」，
 * 回测收益为负如实展示（绿跌），不得取绝对值、不得包装成「策略领先」。
 */

const LS_KEY = 'ss-dashboard-widgets-v1'

/** 组件清单（id 稳定，作为 localStorage 主键；顺序即默认展示顺序）。 */
const WIDGETS: { id: string; title: string; icon: string; Comp: () => ReactElement }[] = [
  { id: 'snapshot', title: '今日决策快照', icon: '📊', Comp: WidgetDailySnapshot },
  { id: 'recommendation', title: '每日荐股', icon: '🎯', Comp: WidgetRecommendation },
  { id: 'breadth', title: '广度温度时序', icon: '🌡️', Comp: WidgetBreadth },
  { id: 'event', title: '事件因子池', icon: '⚡', Comp: WidgetEventPool },
  { id: 'backtest', title: '回测运行记录', icon: '📈', Comp: WidgetBacktestRuns },
]

function loadEnabled(): string[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return WIDGETS.map((w) => w.id)
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      const valid = parsed.filter((id): id is string =>
        typeof id === 'string' && WIDGETS.some((w) => w.id === id),
      )
      return valid
    }
  } catch {
    /* 损坏的 localStorage 回落到默认全开，不静默吞错 */
  }
  return WIDGETS.map((w) => w.id)
}

/** 带符号着色：A 股红涨(#ff4d4f)绿跌(#00d486)，缺失显「—」。 */
function Signed({ value, suffix = '%' }: { value: number | null | undefined; suffix?: string }) {
  if (value === null || value === undefined) return <span className="text-sf-ink-3">—</span>
  const color = value > 0 ? '#ff4d4f' : value < 0 ? '#00d486' : '#9aa0b5'
  const sign = value > 0 ? '+' : ''
  return (
    <span className="tabular-nums font-semibold" style={{ color }}>
      {sign}
      {value.toFixed(2)}
      {suffix}
    </span>
  )
}

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-label text-sf-ink-3">{label}</span>
      <span className="text-body text-sf-ink tabular-nums">{children}</span>
    </div>
  )
}

function WidgetDailySnapshot() {
  const q = useDailySnapshot()
  return (
    <Card title="今日决策快照">
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={false}>
        {q.data ? <SnapshotBody data={q.data} /> : null}
      </QueryState>
    </Card>
  )
}

function SnapshotBody({ data }: { data: DailySnapshot }) {
  const pct = data.position?.pct
  return (
    <div className="flow">
      <div className="text-label text-sf-ink-3">
        数据日 <span className="text-sf-ink tabular-nums">{data.date}</span>
      </div>
      <div className="grid grid-cols-3 gap-3 mt-2">
        <Metric label="温度">{fmtNum(data.temperature)}</Metric>
        <Metric label="周期">{data.cycle ?? '—'}</Metric>
        <Metric label="评分">{fmtNum(data.score)}</Metric>
        <Metric label="仓位">{pct === undefined ? '—' : `${fmtNum(pct)}%`}</Metric>
        <Metric label="仓位档">{data.position?.band ?? '—'}</Metric>
        <Metric label="情绪">{data.bias ?? '—'}</Metric>
      </div>
    </div>
  )
}

function WidgetRecommendation() {
  const q = useDailyRecommendation()
  return (
    <Card title="每日荐股">
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={false}>
        {q.data ? <RecommendationBody data={q.data} /> : null}
      </QueryState>
    </Card>
  )
}

function RecommendationBody({ data }: { data: DailyRecommendation }) {
  // 诚实：status 非可用时如实展示状态与原因，不编造标的列表
  return (
    <div className="flow">
      <div className="text-label text-sf-ink-3">
        生成时间 <span className="text-sf-ink tabular-nums">{data.generated_at ?? '—'}</span>
      </div>
      <div className="mt-2 rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-2">
        <div className="text-body text-sf-ink">
          推荐状态：{data.status ?? '未知'}
        </div>
        {data.reason ? (
          <div className="text-label text-sf-ink-3 mt-1">{data.reason}</div>
        ) : null}
      </div>
      {data.disclaimer ? (
        <p className="text-label text-sf-ink-3 mt-2">{data.disclaimer}</p>
      ) : null}
    </div>
  )
}

function WidgetBreadth() {
  const q = useBreadthTimeseries()
  return (
    <Card title="广度温度时序">
      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={Array.isArray(q.data) && q.data.length === 0}
        emptyLabel="暂无广度时序数据"
        emptyHint="breadth-timeseries 为空数组，未做填充"
      >
        {q.data && q.data.length > 0 ? <BreadthBody rows={q.data} /> : null}
      </QueryState>
    </Card>
  )
}

function BreadthBody({ rows }: { rows: BreadthPoint[] }) {
  const latest = rows[0]
  return (
    <div className="flow">
      <div className="text-label text-sf-ink-3">
        数据日 <span className="text-sf-ink tabular-nums">{latest.date}</span>（共 {rows.length} 期）
      </div>
      <div className="grid grid-cols-3 gap-3 mt-2">
        <Metric label="温度">{fmtNum(latest.temperature)}</Metric>
        <Metric label="上涨/下跌">{`${fmtNum(latest.up_count)} / ${fmtNum(latest.down_count)}`}</Metric>
        <Metric label="涨停/跌停">{`${fmtNum(latest.limit_up)} / ${fmtNum(latest.limit_down)}`}</Metric>
        <Metric label="红盘比">{fmtNum(latest.red_ratio)}%</Metric>
        <Metric label="中位数涨跌">
          <Signed value={latest.median_chg} />
        </Metric>
      </div>
    </div>
  )
}

function WidgetEventPool() {
  const q = useEventPool()
  return (
    <Card title="事件因子池">
      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!q.data && (!q.data.pool || q.data.pool.length === 0)}
        emptyLabel="事件因子池为空"
        emptyHint="pool 为空数组，未做填充"
      >
        {q.data ? <EventBody data={q.data} /> : null}
      </QueryState>
    </Card>
  )
}

function EventBody({ data }: { data: EventPool }) {
  const top = (data.pool ?? []).slice(0, 5)
  return (
    <div className="flow">
      <div className="text-label text-sf-ink-3">
        数据日 <span className="text-sf-ink tabular-nums">{data.date}</span> · 模型{' '}
        {data.model ?? '—'} · 数量 {fmtNum(data.count)}
      </div>
      <ul className="mt-2 space-y-1 text-body">
        {top.map((it) => (
          <li key={`${it.symbol}-${it.rank}`} className="flex justify-between gap-3">
            <span className="text-sf-ink tabular-nums">
              <span className="text-sf-ink-3 mr-2">{it.rank}</span>
              {it.symbol}
            </span>
            <span className="text-sf-ink-2">
              {fmtNum(it.score)} · {it.signal ?? '—'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function WidgetBacktestRuns() {
  const q = useBacktestRuns()
  return (
    <Card title="回测运行记录">
      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!q.data && (!q.data.runs || q.data.runs.length === 0)}
        emptyLabel="暂无回测运行记录"
        emptyHint="runs 为空数组，未做填充"
      >
        {q.data ? <BacktestBody data={q.data} /> : null}
      </QueryState>
    </Card>
  )
}

function BacktestBody({ data }: { data: BacktestRuns }) {
  const run = (data.runs ?? [])[0]
  const s = run?.summary
  if (!run || !s) return <div className="text-label text-sf-ink-3">无可用回测摘要</div>
  return (
    <div className="flow">
      <div className="text-label text-sf-ink-3">
        标的 <span className="text-sf-ink tabular-nums">{s.ticker ?? '—'}</span> · 策略{' '}
        {s.strategy ?? '—'}
      </div>
      <div className="grid grid-cols-3 gap-3 mt-2">
        <Metric label="总收益">
          <Signed value={s.total_return_pct} />
        </Metric>
        <Metric label="最大回撤">
          <Signed value={s.max_drawdown_pct} />
        </Metric>
        <Metric label="夏普">{fmtNum(s.sharpe_ratio)}</Metric>
        <Metric label="胜率">{fmtNum(s.win_rate_pct)}%</Metric>
        <Metric label="交易次数">{fmtNum(s.trade_count)}</Metric>
      </div>
      <p className="text-label text-sf-ink-3 mt-2">
        ⚠️ 回测收益可为负，如实展示（绿跌），不取绝对值、不包装成「策略领先」。
      </p>
    </div>
  )
}

export interface DashboardCustomProps {
  /** 来自 validateSearch 的 ?widgets= 可选覆盖（逗号分隔 id），缺省读 localStorage。 */
  search?: { widgets?: string }
}

export function DashboardCustom({ search }: DashboardCustomProps) {
  // URL 覆盖优先（深链），否则读 localStorage
  const urlWidgets = useMemo(() => {
    if (!search?.widgets) return null
    const ids = search.widgets.split(',').filter((id) => WIDGETS.some((w) => w.id === id))
    return ids.length > 0 ? ids : null
  }, [search?.widgets])

  const [enabled, setEnabled] = useState<string[]>(() => urlWidgets ?? loadEnabled())
  const [editing, setEditing] = useState(false)

  // URL 覆盖时不写 localStorage（深链是只读视图）
  useEffect(() => {
    if (urlWidgets) {
      setEnabled(urlWidgets)
      return
    }
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(enabled))
    } catch {
      /* localStorage 不可用时仅内存态生效，不报错 */
    }
  }, [enabled, urlWidgets])

  const toggle = (id: string) => {
    setEnabled((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const active = WIDGETS.filter((w) => enabled.includes(w.id))

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">自定义看板</h2>
        <span className="text-label text-sf-ink-3">
          组件与顺序由本地保存（localStorage），数据均来自只读端点，未做任何填充
        </span>
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          className="text-label px-3 py-1.5 rounded-tile border border-sf-line ml-auto"
        >
          {editing ? '完成' : '管理组件'}
        </button>
      </div>

      {editing && !urlWidgets ? (
        <div className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
          <div className="text-label text-sf-ink-3 mb-2">勾选要展示的组件（自动保存）</div>
          <div className="flex flex-wrap gap-3">
            {WIDGETS.map((w) => (
              <label key={w.id} className="flex items-center gap-2 text-body text-sf-ink">
                <input
                  type="checkbox"
                  checked={enabled.includes(w.id)}
                  onChange={() => toggle(w.id)}
                  aria-label={`切换组件 ${w.title}`}
                />
                <span>{w.icon} {w.title}</span>
              </label>
            ))}
          </div>
        </div>
      ) : null}

      {active.length === 0 ? (
        <div className="rounded-tile border border-sf-line bg-sf-surface-2 p-6 text-center text-sf-ink-3">
          请在「管理组件」中至少启用一个面板
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mt-3">
          {active.map((w) => {
            const W = w.Comp
            return <W key={w.id} />
          })}
        </div>
      )}
    </div>
  )
}
