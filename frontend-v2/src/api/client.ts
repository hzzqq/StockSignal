import { EnvelopeResponse, LoginData } from './schema'

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
    const env = EnvelopeResponse.parse(await res.json())
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
  headers.set('Content-Type', 'application/json')
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

  const env = EnvelopeResponse.parse(await res.json())
  if (env.status !== 'ok') {
    throw new ApiError(env.code, env.message)
  }
  return env.data as T
}

/** 对外 API：T 为期望的 data 类型 */
export function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  return run<T>(path, init, false)
}
