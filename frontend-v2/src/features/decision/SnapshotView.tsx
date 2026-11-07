import type { DailySnapshot } from '@/api/schemas/read'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { FreshnessBadge } from '@/shared/ui/FreshnessBadge'
import {
  freshnessLevelFromAge,
  freshnessFromStatus,
  type FreshnessLevel,
} from '@/lib/freshness'
import { fmtNum } from '@/lib/format'
import { PositionGauge } from '@/shared/charts/PositionGauge'
import { ScenarioChart } from '@/shared/charts/ScenarioChart'

function freshnessOf(s: DailySnapshot): FreshnessLevel {
  if (typeof s.data_age_days === 'number') return freshnessLevelFromAge(s.data_age_days)
  return freshnessFromStatus(s.data_freshness?.status)
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
  const level = freshnessOf(snapshot)

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

        <Stat label="市场温度" value={fmtNum(snapshot.temperature)} sub={snapshot.cycle} />
        <Stat label="综合评分" value={fmtNum(snapshot.score)} sub={`偏向 ${snapshot.bias ?? '—'}`} />
        <Stat
          label="信心 / 情绪调节"
          value={fmtNum(snapshot.confidence)}
          sub={snapshot.promo_overall != null ? `CYCLE_ADJ ${fmtNum(snapshot.promo_overall)}` : undefined}
        />
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
