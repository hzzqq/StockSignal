import type { PublicUser } from '@/api/schemas/admin'

/**
 * 当前登录用户（角色门控）单一真理源。
 *
 * 登录成功后 LoginPage 把后端 `data.user`（User.to_public）原样存入
 * localStorage('ss_user')；本模块负责读取/解析，供导航与页面门控使用。
 * 解析失败一律返回 null（不抛错、不编造角色），页面据 null 显示无权限空态。
 */

const KEY = 'ss_user'

export function getCurrentUser(): PublicUser | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    const role = (parsed as { role?: unknown } | null)?.role
    if (parsed && typeof parsed === 'object' && (role === 'admin' || role === 'user')) {
      return parsed as PublicUser
    }
    return null
  } catch {
    return null
  }
}

export function getCurrentRole(): 'user' | 'admin' | null {
  return getCurrentUser()?.role ?? null
}

export function isAdmin(): boolean {
  return getCurrentRole() === 'admin'
}

/** 登出时由 guards.clearAuth 调用，清空持久化的用户对象。 */
export function clearCurrentUser(): void {
  localStorage.removeItem(KEY)
}
