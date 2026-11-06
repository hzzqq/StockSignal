import { redirect } from '@tanstack/react-router'

/**
 * 鉴权守卫（W0 最小骨架）。
 * 真实鉴权在 W1 接 client.ts 的 token 校验；此处仅以 localStorage 的 ss_token
 * 是否存在作为「已登录」判据，足以驱动登录链路与来源路由保留。
 */

/** 未登录则重定向到 /login，并保留来源路由到 search.from */
export function requireAuth(from: string): void {
  const token = localStorage.getItem('ss_token')
  if (!token) {
    throw redirect({ to: '/login', search: { from } })
  }
}

/** 登出：清空 token */
export function clearAuth(): void {
  localStorage.removeItem('ss_token')
  localStorage.removeItem('ss_refresh')
}
