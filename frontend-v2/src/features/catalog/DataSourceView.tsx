import { useCallback, useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useDiagnostics } from '@/lib/queries'
import { mocksEnabled } from '@/api/diagnostics'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'

/**
 * 只读端点数据浏览器（/data）。
 *
 * 用途：功能全景页里「v2 暂无等价页面、但有真实只读端点」的 v1 功能，
 * 从这里查看**真实响应数据**。端点清单由后端从 Flask url_map 动态枚举
 * （useDiagnostics），前端不硬编码，需路径参数的端点如实跳过。
 *
 * 诚实红线：
 *  - 真实记录 HTTP 状态 / 信封 status / 耗时，失败直接显示原因，绝不包装成成功；
 *  - data 为 null/空数组就显示空，绝不补 0 或造样例行；
 *  - 数组只展示前 50 行并明示截断，不假装是完整数据；
 *  - MSW 开发态明确标注结果为模拟响应。
 */
const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'
const MAX_ROWS = 50
const MAX_COLS = 12

interface ReadResult {
  path: string
  httpStatus: number | null
  envelopeStatus: string | null
  latencyMs: number | null
  data: unknown
  error: string | null
}

async function fetchRead(path: string, timeoutMs = 8000): Promise<ReadResult> {
  const started = performance.now()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const token = localStorage.getItem('ss_token')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${BASE}${path.replace(/^\/api/, '')}`, {
      method: 'GET', credentials: 'include', headers, signal: controller.signal,
    })
    const latencyMs = Math.round(performance.now() - started)
    let env: { status?: unknown; data?: unknown; message?: unknown } = {}
    try {
      env = (await res.json()) as typeof env
    } catch {
      return {
        path, httpStatus: res.status, envelopeStatus: null, latencyMs,
        data: null, error: '响应不是合法 JSON 信封',
      }
    }
    const envelopeStatus = typeof env.status === 'string' ? env.status : null
    const ok = res.ok && envelopeStatus === 'ok'
    return {
      path, httpStatus: res.status, envelopeStatus, latencyMs,
      data: ok ? (env.data ?? null) : null,
      error: ok
        ? null
        : !res.ok
          ? `HTTP ${res.status}${typeof env.message === 'string' ? `：${env.message}` : ''}`
          : envelopeStatus === null ? '响应缺少信封 status' : `信封 status=${envelopeStatus}`,
    }
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError'
    return {
      path, httpStatus: null, envelopeStatus: null,
      latencyMs: aborted ? timeoutMs : Math.round(performance.now() - started),
      data: null,
      error: aborted ? `超时（>${timeoutMs}ms）` : `请求失败：${err instanceof Error ? err.message : String(err)}`,
    }
  } finally {
    clearTimeout(timer)
  }
}

function cell(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') {
    try {
      const s = JSON.stringify(v)
      return s.length > 120 ? `${s.slice(0, 117)}…` : s
    } catch {
      return '[不可序列化]'
    }
  }
  return String(v)
}

function DataRenderer({ data }: { data: unknown }) {
  if (data === null || data === undefined) {
    return <p className="text-body text-sf-ink-3">端点返回空数据（null）。未展示任何样例行。</p>
  }
  if (Array.isArray(data)) {
    if (data.length === 0) return <p className="text-body text-sf-ink-3">端点返回空数组（0 行）。</p>
    const rows = data.slice(0, MAX_ROWS)
    const cols = Array.from(
      new Set(rows.flatMap((r) => (r && typeof r === 'object' ? Object.keys(r as object) : []))),
    ).slice(0, MAX_COLS)
    if (cols.length === 0) {
      return (
        <div className="overflow-x-auto">
          <table className="cat-table w-full text-body border-collapse">
            <tbody>{rows.map((r, i) => <tr key={i}><td className="py-1.5">{cell(r)}</td></tr>)}</tbody>
          </table>
        </div>
      )
    }
    return (
      <div className="flow">
        <div className="overflow-x-auto">
          <table className="cat-table w-full text-body border-collapse">
            <caption className="sr-only">端点返回的真实数据行</caption>
            <thead>
              <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                {cols.map((c) => <th key={c} scope="col" className="text-left py-1.5 pr-3 font-normal">{c}</th>)}
              </tr>
            </thead>
            <tbody className="text-sf-ink-2">
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-sf-line last:border-0">
                  {cols.map((c) => (
                    <td key={c} className="py-1.5 pr-3 align-top break-all">{cell((r as Record<string, unknown>)?.[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-label text-sf-ink-3">
          共 {data.length} 行{data.length > MAX_ROWS ? `，仅显示前 ${MAX_ROWS} 行（未截断的数据仍在端点）` : '，已全部显示'}；
          列数上限 {MAX_COLS}。
        </p>
      </div>
    )
  }
  if (typeof data === 'object') {
    const entries = Object.entries(data as Record<string, unknown>)
    if (entries.length === 0) return <p className="text-body text-sf-ink-3">端点返回空对象。</p>
    return (
      <div className="overflow-x-auto">
        <table className="cat-table w-full text-body border-collapse">
          <caption className="sr-only">端点返回的真实键值数据</caption>
          <thead>
            <tr className="text-label text-sf-ink-3 border-b border-sf-line">
              <th scope="col" className="text-left py-1.5 pr-3 font-normal">字段</th>
              <th scope="col" className="text-left py-1.5 font-normal">值</th>
            </tr>
          </thead>
          <tbody className="text-sf-ink-2">
            {entries.map(([k, v]) => (
              <tr key={k} className="border-b border-sf-line last:border-0">
                <td className="py-1.5 pr-3 font-mono text-label">{k}</td>
                <td className="py-1.5 break-all">{cell(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return <p className="text-body text-sf-ink-2 break-all">{String(data)}</p>
}

export function DataSourceView({ initialPath = '' }: { initialPath?: string }) {
  const diag = useDiagnostics()
  const [selected, setSelected] = useState(initialPath)
  const [result, setResult] = useState<ReadResult | null>(null)
  const [loading, setLoading] = useState(false)
  const mocked = mocksEnabled()

  const endpoints = (diag.data?.endpoints ?? []).filter((e) => e.probe_path)
  const paths = endpoints.map((e) => e.probe_path as string)

  const load = useCallback(async (path: string) => {
    if (!path) return
    setSelected(path)
    setLoading(true)
    try {
      setResult(await fetchRead(path))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (initialPath && paths.includes(initialPath)) void load(initialPath)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPath, paths.join('|')])

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">只读端点数据浏览器</h2>
        <Link to="/catalog" className="text-body text-sf-accent hover:underline">返回功能全景 →</Link>
      </div>

      {mocked ? (
        <p role="status" className="text-label text-sf-warn">
          当前为开发 Mock 环境：下方响应可能来自 MSW 夹具，不代表真实后端数据。
        </p>
      ) : null}

      <Card title="选择端点" right={<span className="text-label text-sf-ink-3">清单由后端动态枚举</span>}>
        <QueryState
          isLoading={diag.isLoading}
          isError={diag.isError}
          error={diag.error}
          isEmpty={paths.length === 0}
          emptyLabel="后端未提供可查看的只读端点"
        >
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-label text-sf-ink-2">
              只读端点
              <select
                aria-label="只读端点"
                value={selected}
                onChange={(e) => void load(e.target.value)}
                className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
              >
                <option value="">— 请选择 —</option>
                {paths.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void load(selected)}
              disabled={!selected || loading}
              className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-label text-sf-ink hover:border-sf-accent disabled:opacity-50"
            >
              {loading ? '读取中…' : '重新读取'}
            </button>
            <span className="text-label text-sf-ink-3">共 {paths.length} 个可直接读取的端点</span>
          </div>
        </QueryState>
      </Card>

      {result ? (
        <Card
          title={result.path || '读取结果'}
          right={
            <span className="text-label text-sf-ink-3 tabular-nums">
              HTTP {result.httpStatus ?? '—'} · 信封 {result.envelopeStatus ?? '—'} · {result.latencyMs === null ? '—' : `${result.latencyMs} ms`}
            </span>
          }
        >
          {result.error ? (
            <p className="text-body text-sf-warn">读取失败：{result.error}</p>
          ) : (
            <DataRenderer data={result.data} />
          )}
        </Card>
      ) : (
        <Card title="读取结果">
          <p className="text-body text-sf-ink-3">尚未选择端点。选择后将发起一次真实 GET 并显示原始响应数据。</p>
        </Card>
      )}
    </div>
  )
}
