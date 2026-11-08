import { useState } from 'react'
import { useDiagnostics } from '@/lib/queries'
import { probeEndpoints, mocksEnabled } from '@/api/diagnostics'
import type { EndpointProbeResult } from '@/api/schemas/diagnostics'
import type { DiagnosticsFreshnessRow, DiagnosticsProbe } from '@/api/schemas/diagnostics'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { fmtNum } from '@/lib/format'

/**
 * W4-D · 数据源与接口检测页（/diagnostics）——两块检测放同一页。
 *
 * ① 数据源检测：依赖/本地缓存可用性 + 各源真实数据截止日与滞后 + 四源真实网络探测。
 * ② 接口检测：对后端**动态枚举**出的只读端点逐个真实 GET，记录 HTTP 状态 / 信封 / 耗时。
 *
 * 诚实红线：
 *  - 每项检测失败都独立显示 available=false + reason，绝不把空结果包装成「全部正常」；
 *  - as_of 是真实数据截止日，不用探测时刻冒充；缺失显示「—」，不补 0；
 *  - 默认零网络（probe 需显式点击才触发）；
 *  - 开发态 MSW 会拦截请求，页面显式标注「结果为模拟响应，非真实后端连通性」；
 *  - 状态色用 sf-ok / sf-warn（状态语义），绝不误用 A 股涨跌色 ss-up / ss-down。
 */

const PROBE_LABEL: Record<string, string> = {
  L1: 'akshare', L2: 'BaoStock', L3: '新浪财经', L4: '东方财富',
}

function statusText(status: string): string {
  if (status === 'ok' || status === 'fresh') return '正常'
  if (status === 'stale' || status === 'warn') return '滞后'
  if (status === 'unknown') return '未知'
  return status
}

function statusClass(ok: boolean | null): string {
  if (ok === true) return 'text-sf-ok'
  if (ok === false) return 'text-sf-warn'
  return 'text-sf-ink-3'
}

export function DiagnosticsView() {
  const [wantProbe, setWantProbe] = useState(false)
  const [endpointResults, setEndpointResults] = useState<EndpointProbeResult[] | null>(null)
  const [probing, setProbing] = useState(false)
  const [probeError, setProbeError] = useState<string | null>(null)
  const diag = useDiagnostics(wantProbe)
  const mocked = mocksEnabled()

  const data = diag.data
  const endpoints = data?.endpoints ?? []
  const autoPaths = endpoints.filter((e) => e.probe_path).map((e) => e.probe_path as string)
  const skippedCount = endpoints.length - autoPaths.length
  const okEndpoints = endpointResults?.filter((r) => r.ok).length ?? 0

  async function runEndpointProbe() {
    setProbing(true)
    setProbeError(null)
    try {
      setEndpointResults(await probeEndpoints(autoPaths))
    } catch (err) {
      setProbeError(err instanceof Error ? err.message : String(err))
      setEndpointResults([])
    } finally {
      setProbing(false)
    }
  }

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">数据源与接口检测</h2>
        <span className="text-label text-sf-ink-3">主动检测 · 默认不触网</span>
      </div>

      {mocked ? (
        <div role="status" className="flex items-start gap-2 rounded-tile border border-sf-line bg-sf-surface px-4 py-3 text-body text-sf-ink-2">
          <span aria-hidden="true" className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-sf-warn" />
          <span>
            当前为开发 Mock 环境（MSW 已启用）：本页<strong>全部检测结果（含四源网络探测与接口检测）均为模拟数据</strong>，
            既不代表真实后端连通性，也不代表数据源通断。用 <code className="font-mono">start_frontend_v2.bat</code> 启动，
            或设 <code className="font-mono">VITE_ENABLE_MOCKS=false</code> 重启，才会连到真实后端。
          </span>
        </div>
      ) : null}

      <QueryState
        isLoading={diag.isLoading}
        isError={diag.isError}
        error={diag.error}
        isEmpty={!data}
        emptyLabel="无检测数据"
      >
        {data ? (
          <div className="flow">
            {/* ── 汇总 ── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat
                label="依赖与缓存"
                value={data.sources.available ? (data.sources.summary ?? '—') : '不可用'}
                sub={data.sources.available ? `探测于 ${data.sources.checked_at ?? '—'}` : '检测失败'}
              />
              <Stat
                label="数据源时效"
                value={data.freshness.available ? `${data.freshness.rows.length} 源` : '不可用'}
                sub={data.freshness.available
                  ? `正常 ${data.freshness.rows.filter((r) => r.status === 'ok').length} · 滞后 ${data.freshness.rows.filter((r) => r.status !== 'ok' && r.status !== 'unknown').length}`
                  : '检测失败'}
              />
              <Stat label="只读端点" value={endpoints.length} sub={`${autoPaths.length} 个可自动探测`} />
              <Stat
                label="接口连通"
                value={endpointResults ? `${okEndpoints}/${endpointResults.length}` : '未检测'}
                sub={endpointResults ? '本次真实 GET 结果' : '点击「开始检测」'}
              />
            </div>

            {/* ── ① 数据源检测 ── */}
            <section className="flow" aria-labelledby="diag-sources-title">
              <h3 id="diag-sources-title" className="text-title font-medium text-sf-ink-2">① 数据源检测</h3>

              <Card title="依赖与本地缓存" right={
                <span className="text-label text-sf-ink-3">只读探测 · 不触网</span>
              }>
                {data.sources.available ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-body border-collapse">
                      <caption className="sr-only">各数据源依赖可用性与本地缓存状态</caption>
                      <thead>
                        <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                          <th scope="col" className="text-left py-2 pr-3 font-normal">数据源</th>
                          <th scope="col" className="text-left py-2 pr-3 font-normal">状态</th>
                          <th scope="col" className="text-left py-2 pr-3 font-normal">明细</th>
                          <th scope="col" className="text-left py-2 font-normal">缓存表行数</th>
                        </tr>
                      </thead>
                      <tbody className="text-sf-ink-2">
                        {data.sources.items.length > 0 ? data.sources.items.map((it) => (
                          <tr key={it.key} className="border-b border-sf-line last:border-0">
                            <td className="py-1.5 pr-3">{it.label}</td>
                            <td className={`py-1.5 pr-3 ${statusClass(it.ok)}`}>{it.ok ? '可用' : '不可用'}</td>
                            <td className="py-1.5 pr-3 text-sf-ink-3">{it.detail ?? '—'}</td>
                            <td className="py-1.5 text-sf-ink-3">
                              {it.tables && Object.keys(it.tables).length > 0
                                ? Object.entries(it.tables).map(([k, v]) => `${k} ${fmtNum(v)}`).join(' · ')
                                : '—'}
                            </td>
                          </tr>
                        )) : (
                          <tr><td colSpan={4} className="py-3 text-sf-ink-3">未提供逐源明细</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-body text-sf-warn">检测不可用：{data.sources.reason ?? '未知原因'}</p>
                )}
              </Card>

              <Card title="各数据源时效" right={
                <span className="text-label text-sf-ink-3">真实数据截止日</span>
              }>
                {data.freshness.available ? (
                  <FreshnessTable rows={data.freshness.rows} />
                ) : (
                  <p className="text-body text-sf-warn">检测不可用：{data.freshness.reason ?? '未知原因'}</p>
                )}
              </Card>

              <Card
                title={mocked ? '四源网络探测（模拟数据）' : '四源真实网络探测'}
                right={
                  <button
                    type="button"
                    onClick={() => setWantProbe(true)}
                    disabled={diag.isFetching}
                    className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-label text-sf-ink hover:border-sf-accent transition-colors disabled:opacity-50"
                  >
                    {diag.isFetching
                      ? '探测中…'
                      : mocked
                        ? (wantProbe ? '重新查看模拟结果' : '查看模拟探测结果')
                        : (wantProbe ? '重新探测' : '开始真实网络探测')}
                  </button>
                }
              >
                <p className="text-label text-sf-ink-3 mb-3">
                  {mocked
                    ? '当前为 Mock 环境：点击只会读取 MSW 夹具里的模拟结果，不会发出任何真实网络请求；下方通断与耗时均不代表真实数据源状态。'
                    : '默认不触网；点击后后端对 akshare / BaoStock / 新浪 / 东方财富各发一次真实日线请求（约数秒），如实报告通断与耗时。'}
                </p>
                {mocked && data.probe !== null ? (
                  <p role="note" className="text-label text-sf-warn mb-2">
                    以下四源结果来自 MSW 模拟夹具，并非真实探网数据。
                  </p>
                ) : null}
                <ProbeBody probe={data.probe} pending={diag.isFetching && wantProbe} mocked={mocked} />
              </Card>
            </section>

            {/* ── ② 接口检测 ── */}
            <section className="flow" aria-labelledby="diag-api-title">
              <h3 id="diag-api-title" className="text-title font-medium text-sf-ink-2">② 接口检测</h3>
              <Card
                title="只读端点连通性"
                right={
                  <button
                    type="button"
                    onClick={runEndpointProbe}
                    disabled={probing || autoPaths.length === 0}
                    className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-label text-sf-ink hover:border-sf-accent transition-colors disabled:opacity-50"
                  >
                    {probing ? '检测中…' : endpointResults ? '重新检测' : '开始检测'}
                  </button>
                }
              >
                <p className="text-label text-sf-ink-3">
                  端点清单由后端从 Flask 路由表动态枚举（共 {endpoints.length} 个，其中 {skippedCount} 个需路径参数、跳过自动探测）。
                  检测对每个可探测端点发起真实 GET，记录 HTTP 状态、信封 status 与往返耗时；并发上限 4、单请求硬超时 8 秒。
                </p>
                {probeError ? <p className="text-body text-sf-warn mt-2">检测异常：{probeError}</p> : null}
                {endpointResults && endpointResults.length > 0 ? (
                  <div className="overflow-x-auto mt-3">
                    <table className="w-full text-body border-collapse">
                      <caption className="sr-only">只读端点真实 GET 探测结果</caption>
                      <thead>
                        <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                          <th scope="col" className="text-left py-2 pr-3 font-normal">端点</th>
                          <th scope="col" className="text-left py-2 pr-3 font-normal">HTTP</th>
                          <th scope="col" className="text-left py-2 pr-3 font-normal">信封</th>
                          <th scope="col" className="text-right py-2 pr-3 font-normal">耗时</th>
                          <th scope="col" className="text-left py-2 font-normal">结论</th>
                        </tr>
                      </thead>
                      <tbody className="text-sf-ink-2">
                        {endpointResults.map((r) => (
                          <tr key={r.path} className="border-b border-sf-line last:border-0">
                            <td className="py-1.5 pr-3 font-mono text-label break-all">{r.path}</td>
                            <td className="py-1.5 pr-3 tabular-nums">{r.httpStatus ?? '—'}</td>
                            <td className="py-1.5 pr-3">{r.envelopeStatus ?? '—'}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">
                              {r.latencyMs === null ? '—' : `${r.latencyMs} ms`}
                            </td>
                            <td className={`py-1.5 ${statusClass(r.ok)}`}>
                              {r.ok ? '正常' : r.detail}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : endpointResults ? (
                  <p className="text-body text-sf-ink-3 mt-3">没有可自动探测的端点。</p>
                ) : (
                  <p className="text-body text-sf-ink-3 mt-3">尚未检测。点击「开始检测」对 {autoPaths.length} 个端点发起真实请求。</p>
                )}
                {skippedCount > 0 ? (
                  <p className="text-label text-sf-ink-3 mt-2">
                    跳过（需路径参数）：{endpoints.filter((e) => e.needs_params).map((e) => e.path).join(' · ')}
                  </p>
                ) : null}
              </Card>
            </section>

            <p className="text-label text-sf-ink-3">{data.note}</p>
          </div>
        ) : null}
      </QueryState>
    </div>
  )
}

function FreshnessTable({ rows }: { rows: DiagnosticsFreshnessRow[] }) {
  if (rows.length === 0) return <p className="text-body text-sf-ink-3">原始文件未提供逐源时效明细。</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-body border-collapse">
        <caption className="sr-only">各数据源真实数据截止日、滞后天数与状态</caption>
        <thead>
          <tr className="text-label text-sf-ink-3 border-b border-sf-line">
            <th scope="col" className="text-left py-2 pr-3 font-normal">数据源</th>
            <th scope="col" className="text-left py-2 pr-3 font-normal">数据截止日</th>
            <th scope="col" className="text-right py-2 pr-3 font-normal">滞后天数</th>
            <th scope="col" className="text-left py-2 font-normal">状态</th>
          </tr>
        </thead>
        <tbody className="text-sf-ink-2">
          {rows.map((r) => {
            const ok = r.status === 'ok' ? true : r.status === 'unknown' ? null : false
            return (
              <tr key={r.key} className="border-b border-sf-line last:border-0">
                <td className="py-1.5 pr-3">{r.name}</td>
                <td className="py-1.5 pr-3 tabular-nums">{r.as_of ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.lag_days)}</td>
                <td className={`py-1.5 ${statusClass(ok)}`}>{statusText(r.status)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ProbeBody({ probe, pending, mocked }: { probe: DiagnosticsProbe; pending: boolean; mocked: boolean }) {
  if (pending) return <p className="text-body text-sf-ink-3">正在真实探网，请稍候…</p>
  if (probe === null) return <p className="text-body text-sf-ink-3">尚未探测（默认零网络）。</p>
  if (!probe.available) {
    return <p className="text-body text-sf-warn">探测不可用：{probe.reason ?? '未知原因'}</p>
  }
  if (probe.levels.length === 0) return <p className="text-body text-sf-ink-3">探测未返回任何结果。</p>
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {probe.levels.map((lv) => (
        <div key={lv.level} className="rounded-tile bg-sf-surface-2 border border-sf-line px-3.5 py-3">
          <div className="text-label text-sf-ink-3">
            {PROBE_LABEL[lv.level] ?? lv.level}
            {mocked ? <span className="ml-1 text-sf-warn">· 模拟</span> : null}
          </div>
          <div className={`text-kpi font-semibold leading-tight mt-0.5 ${statusClass(lv.ok)}`}>
            {lv.ok ? '通' : '不通'}
          </div>
          <div className="text-label text-sf-ink-3 mt-1 tabular-nums">
            {lv.latency_ms === null || lv.latency_ms < 0 ? '—' : `${lv.latency_ms} ms`}
          </div>
          <div className="text-label text-sf-ink-3 mt-1 break-all" title={lv.detail ?? undefined}>
            {lv.detail ?? '—'}
          </div>
        </div>
      ))}
    </div>
  )
}
