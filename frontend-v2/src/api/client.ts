import { EnvelopeResponse, LoginData, type Envelope } from './schema'

const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'

/** 统一错误：带后端 code，便于上层按 code 分流 */
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly reason: string,
  ) {
    super(reason)
    this.name = 'ApiError'
  }
}

// 401 单飞刷新队列：并发请求同时收到 401 时只发一次 /auth/refresh
let refreshPromise: Promise<boolean> | null = null

/**
 * 读取并校验统一信封。
 *
 * 真实故障（2026-11-09）：旧实现直接 `EnvelopeResponse.parse(await res.json())`，
 * 遇到代理 502/504、网关 HTML 错误页、空响应时抛 SyntaxError / ZodError，
 * HTTP 状态码与响应内容全部丢失，页面只显示 "Unexpected token <"，无法排障。
 * 这里改为：纯文本读取 → JSON 解析 → 信封校验，任一失败都带 HTTP 状态与响应片段。
 */
async function readEnvelope(res: Response): Promise<Envelope> {
  const raw = await res.text()
  let json: unknown
  try {
    json = JSON.parse(raw)
  } catch {
    const snippet = raw.trim().slice(0, 120) || '空响应'
    // 502/503/504 且空响应 = Vite proxy 后端的 Flask 未启动/已退出（ECONNREFUSED
    // 会被代理转成 502），保留原始状态码与片段，仅在末尾给可操作提示。
    // 真机故障（2026-11-22）：老板看到「HTTP 502…空响应」但不知该做什么——
    // 真因只是 5050 后端停了（logs/active_ports_v2.json 还假绿写着 ok=true）。
    const gatewayDown = (res.status === 502 || res.status === 503 || res.status === 504)
      && !raw.trim()
    const hint = gatewayDown
      ? '；后端服务可能未启动，请用 start_frontend_v2.bat 拉起 5050 后重试'
      : ''
    throw new ApiError(
      'http_error',
      `HTTP ${res.status} ${res.statusText}：响应不是 JSON（${snippet}）${hint}`,
    )
  }
  const parsed = EnvelopeResponse.safeParse(json)
  if (!parsed.success) {
    const snippet = JSON.stringify(json).slice(0, 120)
    throw new ApiError(
      'http_error',
      `HTTP ${res.status}：响应不符合统一信封（${snippet}）`,
    )
  }
  return parsed.data
}

function tokenStore() {
  return {
    get access() {
      return localStorage.getItem('ss_token')
    },
    set access(v: string | null) {
      v ? localStorage.setItem('ss_token', v) : localStorage.removeItem('ss_token')
    },
    get refresh() {
      return localStorage.getItem('ss_refresh')
    },
    set refresh(v: string | null) {
      v ? localStorage.setItem('ss_refresh', v) : localStorage.removeItem('ss_refresh')
    },
  }
}

async function doRefresh(): Promise<boolean> {
  const store = tokenStore()
  const refreshToken = store.refresh
  if (!refreshToken) return false
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return false
    const env = await readEnvelope(res)
    if (env.status !== 'ok') return false
    const data = LoginData.parse(env.data) // 抛错即失败，不兜底
    store.access = data.access_token
    if (data.refresh_token) store.refresh = data.refresh_token
    return true
  } catch {
    return false
  }
}

/**
 * 统一请求封装：解包信封 + 401 单飞刷新重试一次。
 * @param retried 内部递归标记，限制只重试一次，防止刷新死循环
 */
async function run<T>(path: string, init: RequestInit, retried: boolean): Promise<T> {
  const store = tokenStore()
  const headers = new Headers(init.headers)
  // multipart（FormData）的 Content-Type 必须由浏览器自动生成（含 boundary），
  // 强制注入 application/json 会破坏 multipart 解析，故 FormData 请求跳过注入。
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (store.access) headers.set('Authorization', `Bearer ${store.access}`)

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })

  if (res.status === 401) {
    if (retried) {
      store.access = null
      store.refresh = null
      throw new ApiError('unauthorized', '认证失败，请重新登录')
    }
    // 单飞：首次 401 触发刷新，后续并发请求复用同一 Promise
    if (!refreshPromise) {
      refreshPromise = doRefresh().finally(() => {
        refreshPromise = null
      })
    }
    const ok = await refreshPromise
    if (!ok) {
      store.access = null
      store.refresh = null
      throw new ApiError('unauthorized', '登录已过期，请重新登录')
    }
    return run<T>(path, init, true)
  }

  const env = await readEnvelope(res)
  if (env.status !== 'ok') {
    throw new ApiError(env.code, env.message)
  }
  return env.data as T
}

/** 对外 API：T 为期望的 data 类型 */
export function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  return run<T>(path, init, false)
}

/**
 * 文件字节下载（parity D · 95 数据导出）：同款 401 单飞刷新，但读取 Blob 而非 JSON 信封。
 *
 * 后端契约（export-bundle zip/excel/pdf）：成功 → 二进制 + Content-Disposition；
 * 失败（全数据集失败 / 格式化崩）→ HTTP 200 + JSON 信封 available=false。
 * 因此：响应是 JSON（或非 2xx）时按信封解析并抛 ApiError（message 即诚实 reason）；
 * 只有真二进制才返回 { blob, filename }。绝不把 JSON 错误信封当作文件字节保存。
 */
export interface BlobDownload {
  blob: Blob
  /** 来自 Content-Disposition（RFC 5987 filename* 优先）；后端未提供时为 null。 */
  filename: string | null
}

async function runBlob(path: string, init: RequestInit, retried: boolean): Promise<BlobDownload> {
  const store = tokenStore()
  const headers = new Headers(init.headers)
  if (store.access) headers.set('Authorization', `Bearer ${store.access}`)

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })

  if (res.status === 401) {
    if (retried) {
      store.access = null
      store.refresh = null
      throw new ApiError('unauthorized', '认证失败，请重新登录')
    }
    if (!refreshPromise) {
      refreshPromise = doRefresh().finally(() => {
        refreshPromise = null
      })
    }
    const ok = await refreshPromise
    if (!ok) {
      store.access = null
      store.refresh = null
      throw new ApiError('unauthorized', '登录已过期，请重新登录')
    }
    return runBlob(path, init, true)
  }

  const contentType = res.headers.get('content-type') ?? ''
  const isJson = contentType.includes('application/json')
  if (!res.ok || isJson) {
    const env = await readEnvelope(res)
    if (env.status !== 'ok') throw new ApiError(env.code, env.message)
    // HTTP 200 + ok 信封 = 业务降级（available=false 等），以业务码抛出交 UI 展示
    throw new ApiError('unavailable', '本次导出无可用数据（后端返回降级说明，无文件）')
  }
  return {
    blob: await res.blob(),
    filename: filenameFromDisposition(res.headers.get('content-disposition')),
  }
}

export function apiFetchBlob(path: string, init: RequestInit = {}): Promise<BlobDownload> {
  return runBlob(path, init, false)
}

/** 从 Content-Disposition 提取下载文件名（RFC 5987 filename* 优先，回退 filename）。 */
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*=(?:UTF-8''|utf-8'')([^;]+)/i.exec(header)
  if (star) {
    try {
      return decodeURIComponent(star[1].replace(/^"|"$/g, ''))
    } catch {
      /* 非法编码回退 filename */
    }
  }
  const plain = /filename="?([^";]+)"?/.exec(header)
  return plain ? plain[1] : null
}
