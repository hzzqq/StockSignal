import type { ReactNode } from 'react'
import type { P1SyncStatus, BacktestRuns, DataRefreshState } from '@/api/schemas/read'
import { useP1SyncStatus, useBacktestRuns, useDataRefreshState } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { fmtNum } from '@/lib/format'

/**
 * W3 后续簇 · 数据与运维状态页（/ops）。
 * 三个独立只读数据源（p1-sync-status / backtest-runs / data-refresh-state），
 * 各自独立四态分发：任一失败不影响另外两块，不连带整页空白。
 *
 * ⚠️ 安全：p1_sync_status.json 原始文件含 target_dir 绝对路径，后端已递归剔除；
 * 本页只渲染 schema 显式声明的字段，绝不遍历/展示 catchall 里的路径类信息。
 * ⚠️ 诚实：回测负收益、负 Sharpe 原样带符号显示，不取绝对值、不做平滑、
 * 不包装成「策略领先」；缺失字段一律 fmtNum → '—'，不补零。
 */
export function SystemStatusView() {
  const sync = useP1SyncStatus()
  const runs = useBacktestRuns()
  const refresh = useDataRefreshState()

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">数据与运维状态</h2>
        <span className="text-label text-sf-ink-3">3 个独立数据源</span>
        <a
          href="/breadth"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          ← 返回广度总览
        </a>
      </div>

      <section className="flow" aria-labelledby="ops-sync-title">
        <h3 id="ops-sync-title" className="text-title font-medium text-sf-ink-2">P1 信号同步</h3>
        <QueryState
          isLoading={sync.isLoading}
          isError={sync.isError}
          error={sync.error}
          isEmpty={!sync.data}
          emptyLabel="无同步状态记录"
        >
          {sync.data ? <SyncBody data={sync.data} /> : null}
        </QueryState>
      </section>

      <section className="flow" aria-labelledby="ops-runs-title">
        <h3 id="ops-runs-title" className="text-title font-medium text-sf-ink-2">回测运行记录</h3>
        <QueryState
          isLoading={runs.isLoading}
          isError={runs.isError}
          error={runs.error}
          isEmpty={!runs.data?.runs?.length}
          emptyLabel="无回测运行记录"
        >
          {runs.data ? <RunsBody data={runs.data} /> : null}
        </QueryState>
      </section>

      <section className="flow" aria-labelledby="ops-refresh-title">
        <h3 id="ops-refresh-title" className="text-title font-medium text-sf-ink-2">数据刷新状态</h3>
        <QueryState
          isLoading={refresh.isLoading}
          isError={refresh.isError}
          error={refresh.error}
          isEmpty={!refresh.data}
          emptyLabel="无刷新状态记录"
        >
          {refresh.data ? <RefreshBody data={refresh.data} /> : null}
        </QueryState>
      </section>
    </div>
  )
}

/** 带符号显示涨跌类数值；A 股价格域红涨绿跌，用 var() 而非通用 UI 色 class。 */
function signed(v: number | null | undefined, digits = 2): ReactNode {
  if (v === null || v === undefined) return fmtNum(v)
  const text = `${v > 0 ? '+' : ''}${v.toFixed(digits)}`
  return (
    <span
      style={{
        color: v > 0 ? 'var(--color-ss-up)' : v < 0 ? 'var(--color-ss-down)' : undefined,
      }}
    >
      {text}
    </span>
  )
}

function SyncBody({ data }: { data: P1SyncStatus }) {
  const health = data.health
  const rows = health?.rows ?? []
  const counts = Object.entries(data.counts ?? {})

  return (
    <div className="flow">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="最近同步" value={data.run_at ?? '—'} />
        <Stat
          label="同步结果"
          value={typeof data.ok === 'boolean' ? (data.ok ? '正常' : '异常') : '—'}
        />
        <Stat
          label="运行模式"
          value={data.mode ?? '—'}
          sub={typeof data.interval_minutes === 'number' ? `每 ${data.interval_minutes} 分钟` : undefined}
        />
        <Stat label="健康检查" value={health?.status ?? '—'} />
      </div>

      {health?.message ? (
        <div
          role="status"
          className="flex items-start gap-2 rounded-tile border border-sf-line bg-sf-surface px-4 py-3 text-body text-sf-ink-2"
        >
          <span aria-hidden="true" className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-sf-accent" />
          <span>{health.message}</span>
        </div>
      ) : null}

      <Card title="同步计数与新鲜度明细">
        <p className="text-label text-sf-ink-3">
          本次计数：
          {counts.length > 0
            ? counts.map(([k, v]) => `${k} ${fmtNum(v)}`).join(' · ')
            : '原始文件未提供计数'}
          {typeof health?.age_days === 'number' ? ` · 最新信号滞后 ${health.age_days} 天` : ''}
        </p>
        {rows.length > 0 ? (
          <div className="overflow-x-auto mt-2">
            <table className="w-full text-body border-collapse">
              <caption className="sr-only">P1 各模型信号副本的最新数据日、滞后天数、结构校验与新鲜度状态</caption>
              <thead>
                <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                  <th scope="col" className="text-left py-2 pr-3 font-normal">模型</th>
                  <th scope="col" className="text-left py-2 pr-3 font-normal">最新数据日</th>
                  <th scope="col" className="text-right py-2 pr-3 font-normal">滞后天数</th>
                  <th scope="col" className="text-left py-2 pr-3 font-normal">结构校验</th>
                  <th scope="col" className="text-left py-2 font-normal">新鲜度</th>
                </tr>
              </thead>
              <tbody className="text-sf-ink-2">
                {rows.map((r) => (
                  <tr key={r.file ?? r.model_key ?? r.latest_date ?? 'row'} className="border-b border-sf-line last:border-0">
                    <td className="py-1.5 pr-3">{r.model_key ?? r.file ?? '—'}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{r.latest_date ?? '—'}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.age_days)}</td>
                    <td className="py-1.5 pr-3">
                      {typeof r.structural_ok === 'boolean' ? (r.structural_ok ? '通过' : '未通过') : '—'}
                    </td>
                    <td className="py-1.5">
                      {typeof r.freshness_ok === 'boolean' ? (
                        r.freshness_ok ? (
                          <span className="text-sf-ok">达标</span>
                        ) : (
                          <span className="text-sf-warn">超 SLA</span>
                        )
                      ) : (
                        <span className="text-sf-ink-3">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-body text-sf-ink-3 mt-2">原始文件未提供逐模型明细。</p>
        )}
        <p className="text-label text-sf-ink-3 mt-2">
          数据来自 data/p1_sync_status.json；绝对路径类字段已由后端递归脱敏，本页不展示。
        </p>
      </Card>
    </div>
  )
}

function RunsBody({ data }: { data: BacktestRuns }) {
  const rows = data.runs
  return (
    <Card title={`运行记录（${rows.length} 次）`}>
      <div className="overflow-x-auto">
        <table className="w-full text-body border-collapse">
          <caption className="sr-only">
            回测运行记录，含运行编号、时间、状态、标的、策略、总收益率、最大回撤、夏普比率与交易笔数
          </caption>
          <thead>
            <tr className="text-label text-sf-ink-3 border-b border-sf-line">
              <th scope="col" className="text-left py-2 pr-3 font-normal">运行时间</th>
              <th scope="col" className="text-left py-2 pr-3 font-normal">标的 / 策略</th>
              <th scope="col" className="text-left py-2 pr-3 font-normal">状态</th>
              <th scope="col" className="text-right py-2 pr-3 font-normal">总收益%</th>
              <th scope="col" className="text-right py-2 pr-3 font-normal">最大回撤%</th>
              <th scope="col" className="text-right py-2 pr-3 font-normal">Sharpe</th>
              <th scope="col" className="text-right py-2 font-normal">交易笔数</th>
            </tr>
          </thead>
          <tbody className="text-sf-ink-2">
            {rows.map((r) => {
              const s = r.summary
              return (
                <tr key={r.run_id} className="border-b border-sf-line last:border-0">
                  <td className="py-1.5 pr-3 tabular-nums" title={r.run_id}>{r.created_at ?? '—'}</td>
                  <td className="py-1.5 pr-3">
                    {s?.ticker ?? '—'} <span className="text-label text-sf-ink-3">/ {s?.strategy ?? '—'}</span>
                  </td>
                  <td className="py-1.5 pr-3">{r.status ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{signed(s?.total_return_pct)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{signed(s?.max_drawdown_pct)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{signed(s?.sharpe_ratio)}</td>
                  <td className="py-1.5 text-right tabular-nums">{fmtNum(s?.trade_count)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-label text-sf-ink-3 mt-2">
        负收益与负 Sharpe 如实保留、未取绝对值；红涨绿跌沿用交易屏价格域语义。
        回测结果不代表未来收益。数据来自 data/backtest_runs.json。
      </p>
    </Card>
  )
}

function RefreshBody({ data }: { data: DataRefreshState }) {
  return (
    <div className="flow">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="上次运行日" value={data.last_run_date ?? '—'} />
        <Stat label="运行结果" value={data.last_result ?? '—'} />
        <Stat label="今日尝试" value={fmtNum(data.attempts_today)} sub="次" />
        <Stat label="CSV 末行" value={data.last_csv_date ?? '—'} />
      </div>
      <Card title="运行明细">
        <p className="text-body text-sf-ink-2">完成时间：{data.finished_at ?? '—'}</p>
        <p className="text-label text-sf-ink-3 mt-2 font-mono break-all">
          {data.detail ?? '原始文件未提供明细'}
        </p>
        <p className="text-label text-sf-ink-3 mt-2">
          detail 为刷新脚本原始输出，未做解析或美化；数据来自 data/data_refresh_state.json。
        </p>
      </Card>
    </div>
  )
}
