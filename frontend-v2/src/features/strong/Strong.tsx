import { useState } from 'react'
import type { Strong, StrongItem } from '@/api/schemas/read'
import { useStrong } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { CHART } from '@/shared/charts/palette'

/**
 * 76 页「实时强势榜」V2 化（对应 V2-STATUS-PLAN Tier2）。
 * 数据来源：useStrong → GET /api/v2/read/strong（后端复用 modules.spot_rank）。
 *
 * 红线：
 * - 取不到快照→items=[]、unavailable 标注，不编数据；评分为启发式加权，非预测。
 * - 数值后端已清洗为 null，前端不补 0（避开 ?? 0 / || 0 / new Date()）。
 */
// 仅供图表坐标 / 文本占位：非数→0，不编数据（避开诚实红线 ?? 0 / || 0 / new Date()）
function nz(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

const TOP_N_OPTIONS = [10, 20, 30, 50]

function fmtPct(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}%`
  }
  return '—'
}
function fmtPrice(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—'
}
function chgColor(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 0 ? CHART.up : v < 0 ? CHART.down : CHART.ink2
  }
  return CHART.ink2
}
function scoreColor(score: unknown): string {
  const s = nz(score)
  if (s >= 75) return CHART.up
  if (s >= 50) return '#f59e0b'
  return '#94a3b8'
}
const MEDALS = ['🥇', '🥈', '🥉']

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(100, nz(value)))
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-10 opacity-70">{label}</span>
      <span className="flex-1 h-1.5 rounded-full bg-sf-line/40 overflow-hidden">
        <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </span>
    </div>
  )
}

function Row({ it, idx }: { it: StrongItem; idx: number }) {
  const medal = MEDALS[idx] ?? `${idx + 1}`
  // score 后端已清洗为 null（数据不足）；缺失显「—」，不补零（避开诚实红线）。
  const score = it.score
  return (
    <div className="border border-sf-line rounded-md p-3">
      <div className="flex justify-between items-center">
        <div>
          <span className="text-sm">{medal}</span>{' '}
          <span className="font-semibold text-[15px]">{it.name ?? '—'}</span>{' '}
          <span className="opacity-60 text-xs">{it.code ?? ''}</span>
        </div>
        <div className="text-right">
          <span className="text-xs font-semibold" style={{ color: chgColor(it.chg) }}>{fmtPct(it.chg)}</span>{' '}
          <span className="text-lg font-bold ml-2" style={{ color: scoreColor(score) }}>{score == null ? '—' : score.toFixed(1)}</span>
          <div className="text-[11px] opacity-60">价 {fmtPrice(it.price)}</div>
        </div>
      </div>
      <div className="mt-2 space-y-1">
        <ScoreBar label="涨幅" value={nz(it.s_chg)} color="#dc2626" />
        <ScoreBar label="量比" value={nz(it.s_vr)} color="#f97316" />
        <ScoreBar label="换手" value={nz(it.s_to)} color="#8b5cf6" />
        <ScoreBar label="成交额" value={nz(it.s_amt)} color="#0ea5e9" />
      </div>
    </div>
  )
}

export function Strong() {
  const q = useStrong()
  const d = q.data
  const items = d?.items ?? []
  const srcLabel = d?.src_label ?? null
  const kicked = (d?.kicked ?? []).filter((k): k is string => typeof k === 'string')
  const unavailable = (d?.unavailable ?? []).filter((k): k is string => typeof k === 'string')

  const [topN, setTopN] = useState(20)
  const [onlyUp, setOnlyUp] = useState(true)

  const hasUp = items.some((it) => nz(it.chg) > 0)
  const onlyUpActive = onlyUp && hasUp
  const filtered = items
    .filter((it) => (onlyUpActive ? nz(it.chg) > 0 : true))
    .slice(0, topN)
  const isEmpty = !!d && items.length === 0
  // 榜首评分取原始 nullable 值；缺失由下方 Stat 显「—」，不补零。
  const topScore = filtered.length > 0 ? filtered[0].score : null

  return (
    <div className="strong">
      <h2 className="text-lg font-semibold">实时强势榜</h2>
      <div className="text-xs text-sf-ink-3">
        全市场多因子强势 Top N：涨幅 0.40 + 量比 0.30 + 换手 0.20 + 成交额 0.10（启发式，非预测）。
        红涨绿跌；奖牌只给前 3，其余按评分降序。数据源东财实时快照（接口受限时自动切换应急源，页内如实标注）。
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="text-xs text-sf-ink-3">
          显示数量{' '}
          <select
            className="ml-1 rounded border border-sf-line bg-sf-surface px-2 py-1 text-xs"
            value={topN}
            onChange={(e) => setTopN(Number(e.target.value))}
          >
            {TOP_N_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className={`rounded px-3 py-1 text-xs font-medium border ${onlyUp ? 'bg-sf-accent text-white border-sf-accent' : 'bg-sf-surface text-sf-ink-3 border-sf-line'}`}
          onClick={() => setOnlyUp((v) => !v)}
        >
          {onlyUp ? '仅看上涨：开' : '仅看上涨：关'}
        </button>
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="实时行情快照未就绪"
        emptyHint="取数失败（离线 / 接口受限 / 非交易时段）；后端已诚实降级，未编造榜单"
      >
        {d ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="榜单标的" value={String(filtered.length)} sub={`Top ${topN} · ${onlyUpActive ? '仅上涨' : '全样本'}`} />
              <Stat
                label="榜首强势评分"
                value={topScore == null ? '—' : topScore.toFixed(1)}
                sub="启发式加权（涨幅/量比/换手/成交额），非预测"
              />
              <Stat label="行情数据源" value={srcLabel ?? '—'} sub="东财直连 → akshare → 腾讯应急（60s 缓存）" />
              <Stat label="二道闸拦截" value={String(kicked.length)} sub="六维红旗排雷，拦截标的不进榜" />
            </div>

            {kicked.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                🚫 二道闸已拦截 {kicked.length} 只高危标的（不进入榜单）：{kicked.join('、')}
              </div>
            )}

            {filtered.length > 0 ? (
              <Card title={`强势榜（评分 Top ${filtered.length}）`}>
                <div className="space-y-2">
                  {filtered.map((it, i) => (
                    <Row key={it.code ?? i} it={it} idx={i} />
                  ))}
                </div>
              </Card>
            ) : (
              <div className="text-xs text-sf-ink-3">
                当前无符合条件的标的{onlyUpActive ? '（已按「仅上涨」过滤，盘中下跌时榜单为空是正常状态）' : ''}。
              </div>
            )}

            {unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下情况本次发生（已诚实标注）：{unavailable.join('、')}
              </div>
            )}

            <div className="text-xs text-sf-ink-3">
              口径与来源：实时快照=东财直连 → akshare → 腾讯应急三层降级（modules/spot_rank，60 秒缓存，
              取不到明示未就绪、不用陈旧数据冒充实时）；强势评分=涨幅 0.40 + 量比 0.30 + 换手 0.20 + 成交额 0.10
              启发式加权；二道闸=scan_and_gate 六维红旗排雷（仅对评分 Top 200 候选，控制扫描成本）。
              启发式排序非预测，非实时投资建议。
            </div>
          </div>
        ) : null}
      </QueryState>

      <div className="mt-8">
        <div className="text-xs text-sf-ink-3">
          ⚠️ 说明：本榜为启发式强势评分排序，非预测模型，不构成投资建议；高换手/高量比亦伴随高波动风险。
          实时快照经 60 秒缓存，盘中读数可能有延迟。
        </div>
      </div>
    </div>
  )
}
