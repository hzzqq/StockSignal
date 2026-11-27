import type { DailySnapshot } from '@/api/schemas/read'
import { Card } from '@/shared/ui/Card'
import { FreshnessBadge } from '@/shared/ui/FreshnessBadge'
import { freshnessOfSnapshot } from '@/lib/freshness'
import { fmtNum } from '@/lib/format'
import { PositionGauge } from '@/shared/charts/PositionGauge'
import { ScenarioChart } from '@/shared/charts/ScenarioChart'

/** 涨跌语义色：A 股红涨绿跌（价格/涨跌域专用，见 tokens.css 红线）。 */
const UP = 'var(--color-ss-up)'
const DOWN = 'var(--color-ss-down)'

/** 卡头大数字 + 档位徽章：默认品牌渐变 pill，传 badgeColor 时用语义纯色（bias 多红/空绿）。 */
function HeadValue({ value, badge, badgeColor }: { value: string; badge?: string; badgeColor?: string }) {
  return (
    <div className="flex items-baseline gap-2 mt-0.5">
      <span className="text-kpi font-semibold leading-tight tabular-nums">{value}</span>
      {badge && (
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-full text-white whitespace-nowrap"
          style={
            badgeColor
              ? { background: badgeColor }
              : { background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))' }
          }
        >
          {badge}
        </span>
      )}
    </div>
  )
}

/** 卡身明细行：label 左对齐 + 值右对齐（可选涨跌语义色），缺失显「—」。 */
function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-sf-ink-3">{label}</span>
      <span className="font-medium tabular-nums" style={color ? { color } : undefined}>
        {value}
      </span>
    </div>
  )
}

/** 信心方向徽章色：偏多红 / 偏空绿 / 中性灰（涨跌语义，非错误语义）。 */
function biasColor(bias: string | undefined): string | undefined {
  if (!bias) return undefined
  if (bias.includes('多')) return UP
  if (bias.includes('空')) return DOWN
  return undefined
}

/** 情绪调节 CYCLE_ADJ 徽章：正=红（加仓方向）/ 负=绿 / 缺失灰。 */
function adjColor(v: number | undefined): string | undefined {
  if (v == null) return undefined
  return v > 0 ? UP : v < 0 ? DOWN : undefined
}

/** 数值安全格式化：null/undefined/非有限 -> 「—」（诚实红线，不补零）。 */
function nv(v: unknown): string {
  if (v === null || v === undefined) return '—'
  const f = typeof v === 'string' ? Number(v) : v
  if (typeof f !== 'number' || !Number.isFinite(f)) return '—'
  return fmtNum(f)
}

/** 带符号百分比：+5.72% / −3.40% / —（缺失）。 */
function pctSigned(v: unknown): string {
  const f = typeof v === 'string' ? Number(v) : (v as number)
  if (typeof f !== 'number' || !Number.isFinite(f)) return '—'
  return `${f >= 0 ? '+' : '−'}${Math.abs(f).toFixed(2)}%`
}

const INDICATOR_LABELS: Record<string, string> = {
  up_count: '上涨家数',
  down_count: '下跌家数',
  limit_up: '涨停',
  limit_down: '跌停',
  red_ratio: '红盘比',
  median_chg: '中位涨跌幅',
  turnover_amt: '成交额(亿)',
  hb_wave10: '10日波动',
  connect_hl: '连板高度',
  connect_2b: '二板数',
  zt_fail_count: '炸板数',
  fc_ratio: '封板率',
}

/**
 * 决策快照可视化（纯展示组件，不取数、不计算）。
 * 同时服务于「今日决策面板」（54）与「决策回放」（97）两页。
 */
export function SnapshotView({ snapshot }: { snapshot: DailySnapshot }) {
  const pos = snapshot.position
  const ef = snapshot.event_factor
  const df = snapshot.data_freshness
  const ind = snapshot.indicators ?? {}
  const level = freshnessOfSnapshot(snapshot)

  return (
    <div className="flow">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <div className="text-xs text-sf-ink-3">权威数据日</div>
          <div className="text-lg font-semibold">{snapshot.date}</div>
        </div>
        <FreshnessBadge level={level} />
        {snapshot.as_of && (
          <div className="text-xs text-sf-ink-3">as_of {snapshot.as_of}</div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card title="仓位建议">
          <PositionGauge pct={pos?.pct ?? null} color={pos?.color ?? null} />
          {pos?.band && <div className="text-sm text-sf-ink-2 text-center -mt-2">{pos.band}</div>}
          {pos?.reasons && pos.reasons.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-sf-ink-2 list-disc list-inside">
              {pos.reasons.slice(0, 6).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
        </Card>

        {/* 市场温度卡：温度 + 周期档位徽章 + 盘面涨跌骨架（2026-11-22 老板需求：完善空洞卡） */}
        <Card title="市场温度">
          <HeadValue value={nv(snapshot.temperature)} badge={snapshot.cycle || undefined} />
          <div className="mt-2 space-y-1.5">
            <Row
              label="红盘比"
              value={pctSigned(ind.red_ratio)}
              color={
                typeof ind.red_ratio === 'number' && Number.isFinite(ind.red_ratio)
                  ? ind.red_ratio >= 50
                    ? UP
                    : DOWN
                  : undefined
              }
            />
            <Row label="涨停家数" value={nv(ind.limit_up)} color={nv(ind.limit_up) === '—' ? undefined : UP} />
            <Row label="跌停家数" value={nv(ind.limit_down)} color={nv(ind.limit_down) === '—' ? undefined : DOWN} />
            <Row
              label="中位涨跌幅"
              value={pctSigned(ind.median_chg)}
              color={
                typeof ind.median_chg === 'number' && Number.isFinite(ind.median_chg)
                  ? ind.median_chg >= 0
                    ? UP
                    : DOWN
                  : undefined
              }
            />
          </div>
        </Card>

        {/* 综合评分卡：评分 + 偏向语义徽章（多红/空绿）+ 情景概率摘要（数据缺失行显「—」） */}
        <Card title="综合评分">
          <HeadValue
            value={nv(snapshot.score)}
            badge={snapshot.bias ? `偏向 ${snapshot.bias}` : undefined}
            badgeColor={biasColor(snapshot.bias)}
          />
          <div className="mt-2 space-y-1.5">
            {!snapshot.bias && <Row label="偏向" value="偏向 —" />}
            {(snapshot.scenario ?? []).slice(0, 3).map((s, i) => (
              <Row
                key={i}
                label={s.name ?? `情景${i + 1}`}
                value={s.prob != null ? `${Math.round(s.prob)}%` : '—'}
              />
            ))}
            {(snapshot.scenario ?? []).length === 0 && <Row label="情景概率" value="—" />}
          </div>
        </Card>

        {/* 信心 / 情绪调节卡：信心 + CYCLE_ADJ + 情绪类盘面支撑 */}
        <Card title="信心 / 情绪调节">
          <HeadValue value={nv(snapshot.confidence)} />
          <div className="mt-1">
            <Row
              label="情绪调节"
              value={snapshot.promo_overall != null ? `CYCLE_ADJ ${fmtNum(snapshot.promo_overall)}` : '—'}
              color={adjColor(snapshot.promo_overall)}
            />
          </div>
          <div className="mt-2 space-y-1.5">
            <Row
              label="连板高度 / 总数"
              value={`${snapshot.ladder?.max_boards ?? '—'} / ${snapshot.ladder?.total_connect ?? '—'}`}
            />
            <Row label="炸板率" value={pctSigned(ind.zt_fail_ratio)} />
            {/* 诚实红线：事件因子不可用整行不渲染（守卫禁止出现「多头」字样，不编造） */}
            {ef?.available && (
              <Row
                label="事件因子多头"
                value={`${ef.long_count ?? '—'} 只${ef.adj != null ? ` · 调节 ${ef.adj > 0 ? '+' : ''}${ef.adj}` : ''}`}
              />
            )}
          </div>
        </Card>
      </div>

      {snapshot.scenario && snapshot.scenario.length > 0 && (
        <Card title="情景概率">
          <ScenarioChart items={snapshot.scenario} />
        </Card>
      )}

      <Card title="盘面指标">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {Object.entries(INDICATOR_LABELS).map(([k, label]) => (
            <div key={k} className="rounded-tile bg-sf-surface-2 border border-sf-line px-3 py-2">
              <div className="text-xs text-sf-ink-3">{label}</div>
              <div className="text-base font-medium">{fmtNum(ind[k])}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card title="连板梯队">
          <div className="text-sm text-sf-ink-2">
            最高板 <span className="text-sf-ink font-semibold">{snapshot.ladder?.max_boards ?? '—'}</span>
            {' · '}连板总数 <span className="text-sf-ink font-semibold">{snapshot.ladder?.total_connect ?? '—'}</span>
          </div>
        </Card>
        <Card title="事件因子">
          {ef?.available ? (
            <div className="text-sm text-sf-ink-2">
              多头 {ef.long_count ?? '—'} 只
              {ef.adj != null && <span className="ml-2">调节 {ef.adj}</span>}
              {ef.as_of && <div className="text-xs text-sf-ink-3 mt-1">as_of {ef.as_of}</div>}
            </div>
          ) : (
            <div className="text-sm text-sf-ink-3">事件因子不可用</div>
          )}
        </Card>
        <Card title="数据新鲜度">
          {df?.sources ? (
            <ul className="space-y-1 text-xs text-sf-ink-2">
              {Object.entries(df.sources).map(([name, src]) => (
                <li key={name} className="flex justify-between gap-2">
                  <span>{name}</span>
                  <span>
                    {src.lag_days != null ? `${src.lag_days}天` : '—'} · {src.status ?? '—'}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-sf-ink-3">无新鲜度明细</div>
          )}
        </Card>
      </div>
    </div>
  )
}
