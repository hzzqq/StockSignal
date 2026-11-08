import { apiFetch } from './client'
import { DiagnosticsSchema, type Diagnostics, type EndpointProbeResult } from './schemas/diagnostics'

const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'

/** 数据源 + 接口检测总览；probe=true 时后端才真实探网（约数秒）。 */
export async function getDiagnostics(probe = false): Promise<Diagnostics> {
  const qs = probe ? '?probe=1' : ''
  const data = await apiFetch<unknown>(`/v2/read/diagnostics${qs}`)
  return DiagnosticsSchema.parse(data)
}

/**
 * 对单个只读端点发起**真实 GET**（不经 apiFetch 的自动 401 刷新，保留原始 HTTP 状态）。
 *
 * 诚实口径：记录真实 HTTP 状态、信封 status、耗时与错误原因；任一失败如实标注，
 * 不把超时/网络错误包装成成功，也不臆造状态码。
 *
 * 注：开发态若启用 MSW，请求会被拦截并返回 Mock 响应 —— 页面会显式标注该环境，
 * 说明此时结果不代表真实后端连通性。
 */
async function probeOne(path: string, timeoutMs: number): Promise<EndpointProbeResult> {
  const started = performance.now()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const token = localStorage.getItem('ss_token')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${BASE}${path.replace(/^\/api/, '')}`, {
      method: 'GET',
      credentials: 'include',
      headers,
      signal: controller.signal,
    })
    const latencyMs = Math.round(performance.now() - started)
    let envelopeStatus: string | null = null
    try {
      const env = (await res.json()) as { status?: unknown }
      envelopeStatus = typeof env.status === 'string' ? env.status : null
    } catch {
      envelopeStatus = null
    }
    const ok = res.ok && envelopeStatus === 'ok'
    return {
      path,
      httpStatus: res.status,
      envelopeStatus,
      ok,
      latencyMs,
      detail: ok
        ? '正常'
        : !res.ok
          ? `HTTP ${res.status}`
          : envelopeStatus === null
            ? '响应非 JSON 信封'
            : `信封 status=${envelopeStatus}`,
    }
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError'
    return {
      path,
      httpStatus: null,
      envelopeStatus: null,
      ok: false,
      latencyMs: aborted ? timeoutMs : Math.round(performance.now() - started),
      detail: aborted ? `超时（>${timeoutMs}ms）` : `请求失败：${err instanceof Error ? err.message : String(err)}`,
    }
  } finally {
    clearTimeout(timer)
  }
}

/**
 * 批量探测：有界并发（默认 4，避免一次打满全部端点），硬超时 8s/个。
 * 需路径参数的端点由后端标注 needs_params=true，前端跳过并如实说明，不编造参数。
 */
export async function probeEndpoints(
  paths: string[],
  concurrency = 4,
  timeoutMs = 8000,
): Promise<EndpointProbeResult[]> {
  const results: EndpointProbeResult[] = new Array(paths.length)
  let cursor = 0
  async function worker() {
    while (cursor < paths.length) {
      const i = cursor++
      results[i] = await probeOne(paths[i], timeoutMs)
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, Math.max(paths.length, 1)) }, worker))
  return results
}

/** 开发态 MSW 是否启用（与 main.tsx 的 bootstrap 判定保持一致）。 */
export function mocksEnabled(): boolean {
  const env = import.meta.env as Record<string, unknown>
  return Boolean(import.meta.env.DEV) && env['VITE_ENABLE_MOCKS'] !== 'false'
}
