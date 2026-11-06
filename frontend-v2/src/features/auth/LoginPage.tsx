import { useState, type FormEvent } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { login } from '@/api/endpoints'
import { clearAuth } from '@/app/guards'
import type { AppPath } from '@/nav/nav'

const KNOWN_PATHS: AppPath[] = [
  '/',
  '/decision',
  '/replay',
  '/morning',
  '/p1',
  '/recommend',
  '/paper',
  '/alerts',
  '/webapps',
]

export function LoginPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/login' })
  const rawFrom = typeof search.from === 'string' && search.from.startsWith('/') ? search.from : '/'
  const from: AppPath = (KNOWN_PATHS as string[]).includes(rawFrom) ? (rawFrom as AppPath) : '/'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (!username || !password) {
      setError('请输入用户名和密码')
      return
    }

    setLoading(true)
    try {
      // 契约类型化登录（endpoints.login 内部用 LoginRequest/LoginData 严格校验）
      const result = await login(username, password)
      localStorage.setItem('ss_token', result.access_token)
      if (result.refresh_token) localStorage.setItem('ss_refresh', result.refresh_token)
      // 保留来源路由：登录后回到触发登录的页面（from 由守卫写入 search）
      navigate({ to: from })
    } catch (err) {
      clearAuth()
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-sf-bg text-sf-txt">
      <form
        onSubmit={onSubmit}
        className="w-80 p-6 rounded-xl bg-sf-card border border-sf-border space-y-4"
      >
        <h1 className="text-xl font-semibold">StockSignal 登录</h1>
        <input
          className="w-full px-3 py-2 rounded bg-sf-bg border border-sf-border outline-none focus:border-ss-up"
          placeholder="用户名"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          className="w-full px-3 py-2 rounded bg-sf-bg border border-sf-border outline-none focus:border-ss-up"
          placeholder="密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-ss-down text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 rounded bg-ss-up text-white disabled:opacity-50"
        >
          {loading ? '登录中…' : '登录'}
        </button>
      </form>
    </div>
  )
}
