import { useState, type FormEvent } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { login, register } from '@/api/endpoints'
import { clearAuth } from '@/app/guards'
import { NAV, UTILITY_PATHS } from '@/nav/nav'
import { MarketBriefing } from './MarketBriefing'
import { LoginWelcome } from './LoginWelcome'

/**
 * 登录页（沿用第一版 v1 的双态设计）。
 *
 * 两态（老板 2026-11-08 拍板「欢迎页 + 分栏两态都要」）：
 *   1. **欢迎态**：v1 `modules/session.py::_render_login_gate()` 的品牌门禁页
 *      （Hero 渐变大标题 + 品牌卡 + 演示账号徽章 + 渐变主按钮 + 脚注）。
 *      → 见 `LoginWelcome.tsx`。
 *   2. **登录态**：v1 `pages/90_登录.py` 的「左行情台 ｜ 右表单」分栏。
 *      左栏 = 合并组件 `MarketBriefing`（品牌卡 + 资金温度 + 今日市场 +
 *      上证分时 + 今日推荐；2026-11-21 老板需求：三块合一 + 分时图 +
 *      「AI 信号」改「今日推荐」）；数据取三个公开摘要端点（无鉴权脱敏只读）。
 *      右栏 = 登录/注册双模式表单（2026-11-21 接入开放注册，后端
 *      POST /api/auth/register 早已存在）+ 演示账号一键填充。
 *
 * 注册语义（诚实红线）：
 *   - 注册成功**不自动登录**（后端不发 token）——回填用户名并提示「请登录」；
 *   - 角色固定 user（后端 register_user 硬编码，前端无提权入口）；
 *   - 验证码登录仍不做假功能（依赖短信网关，未接入即不显示假 Tab）。
 *
 * 缺陷修复（本轮附带）：
 *   - `KNOWN_PATHS` 从 NAV 派生（单一真理源，不再手抄）；
 *   - 表单可访问性：`<label>`、`autoComplete`、`aria-invalid` + `aria-describedby`。
 */
export function LoginPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/login' })
  const rawFrom = typeof search.from === 'string' && search.from.startsWith('/') ? search.from : '/'
  // 单一真理源：从 NAV 派生全部合法路径（不再手抄子集）
  // NAV + 底部固定入口（UTILITY_PATHS 单一真理源）：漏一条就会把用户静默甩回首页。
  const knownPaths = new Set<string>([
    ...NAV.flatMap((g) => g.items.map((it) => it.to)),
    ...UTILITY_PATHS,
  ])
  const from = knownPaths.has(rawFrom) ? rawFrom : '/'

  const [stage, setStage] = useState<'welcome' | 'form'>('welcome')
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNotice(null)

    if (!username || !password) {
      setError('请输入用户名和密码')
      return
    }

    setLoading(true)
    try {
      if (mode === 'register') {
        if (password !== confirm) {
          setError('两次输入的密码不一致')
          return
        }
        const user = await register(username, password, confirm)
        // 注册成功不自动登录（后端不发 token）：回填用户名 + 提示登录，绝不假装已登录。
        setMode('login')
        setConfirm('')
        setNotice(`注册成功（${user.username}），请登录`)
        setPassword('')
      } else {
        // 契约类型化登录（endpoints.login 内部用 LoginRequest/LoginData 严格校验）
        const result = await login(username, password)
        localStorage.setItem('ss_token', result.access_token)
        if (result.refresh_token) localStorage.setItem('ss_refresh', result.refresh_token)
        // 持久化当前用户（含角色），供导航与页面门控；MSW 缺 user 时不报错。
        if (result.user) localStorage.setItem('ss_user', JSON.stringify(result.user))
        // 保留来源路由：登录后回到触发登录的页面（from 由守卫写入 search）
        navigate({ to: from as '/' })
      }
    } catch (err) {
      if (mode === 'login') clearAuth()
      setError(err instanceof Error ? err.message : mode === 'register' ? '注册失败' : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  if (stage === 'welcome') {
    return <LoginWelcome onLogin={() => setStage('form')} />
  }

  const isRegister = mode === 'register'

  return (
    <div className="min-h-screen overflow-y-auto flex items-center justify-center bg-sf-bg px-6 py-10 text-sf-ink">
      <div className="w-full max-w-[980px] grid grid-cols-1 md:grid-cols-[0.46fr_0.54fr] gap-8">
        {/* ── 左栏：合并行情台（品牌 + 温度 + 市场 + 上证分时 + 今日推荐） ── */}
        <MarketBriefing />

        {/* ── 右栏：登录 / 注册表单 ── */}
        <div className="max-w-[420px] w-full mx-auto">
          <div className="text-center mb-6">
            <h1 className="text-[2.2rem] font-black leading-tight mb-1.5">
              🔑 {isRegister ? '注册 StockSignal' : '登录 StockSignal'}
            </h1>
            <p className="text-[0.95rem] text-sf-ink-2 m-0">
              {isRegister
                ? '注册后使用新账号登录；新账号为普通用户角色'
                : '登录后解锁行情看板、个股分析、形态选股等全部功能'}
            </p>
          </div>

          {/* 登录 / 注册双模式切换 */}
          <div
            className="flex rounded-tile border border-sf-line bg-sf-surface-2 p-1 mb-4 max-w-[420px] mx-auto"
            role="tablist"
            aria-label="登录或注册"
          >
            {(['login', 'register'] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => {
                  setMode(m)
                  setError(null)
                  setNotice(null)
                }}
                className={`flex-1 py-1.5 rounded-tile border-0 cursor-pointer text-label font-semibold ${
                  mode === m ? 'text-white' : 'text-sf-ink-2 bg-transparent hover:text-sf-ink'
                }`}
                style={
                  mode === m
                    ? { background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))' }
                    : undefined
                }
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          <form
            onSubmit={onSubmit}
            className="rounded-card bg-sf-surface border border-sf-line p-6 space-y-4"
          >
            <div>
              <label htmlFor="login-username" className="block text-label text-sf-ink-2 mb-1.5">
                用户名
              </label>
              <input
                id="login-username"
                name="username"
                autoComplete="username"
                className="w-full px-3 py-2 rounded-tile bg-sf-surface-2 border border-sf-line outline-none focus:border-sf-accent"
                placeholder={isRegister ? '2-32 位：字母/数字/下划线/中文' : '请输入用户名'}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'login-error' : undefined}
              />
            </div>

            <div>
              <label htmlFor="login-password" className="block text-label text-sf-ink-2 mb-1.5">
                密码
              </label>
              <input
                id="login-password"
                name="password"
                type="password"
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                className="w-full px-3 py-2 rounded-tile bg-sf-surface-2 border border-sf-line outline-none focus:border-sf-accent"
                placeholder={isRegister ? '至少 8 位' : '请输入密码'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'login-error' : undefined}
              />
            </div>

            {isRegister && (
              <div>
                <label htmlFor="login-confirm" className="block text-label text-sf-ink-2 mb-1.5">
                  确认密码
                </label>
                <input
                  id="login-confirm"
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  className="w-full px-3 py-2 rounded-tile bg-sf-surface-2 border border-sf-line outline-none focus:border-sf-accent"
                  placeholder="再输入一次密码"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? 'login-error' : undefined}
                />
              </div>
            )}

            {error && (
              <p id="login-error" role="alert" className="text-sf-danger text-body">
                {error}
              </p>
            )}
            {notice && !error && (
              <p role="status" className="text-body" style={{ color: 'var(--color-ss-up)' }}>
                {notice}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-tile font-bold text-white border-0 cursor-pointer disabled:opacity-50"
              style={{
                background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))',
              }}
            >
              {loading ? (isRegister ? '注册中…' : '登录中…') : isRegister ? '立即注册' : '立即登录'}
            </button>
          </form>

          {/* 演示账号一键填充（登录模式专用） */}
          {!isRegister && (
            <div className="flex gap-2 flex-wrap mt-3.5">
              <button
                type="button"
                onClick={() => {
                  setUsername('demo')
                  setPassword('Demo@123')
                  setError(null)
                }}
                className="rounded-tile px-3 py-1.5 text-label border border-sf-line bg-sf-surface-2 text-sf-ink-2 hover:border-sf-accent"
              >
                🧪 一键填演示账号
              </button>
              <button
                type="button"
                onClick={() => {
                  setUsername('admin')
                  setPassword('Admin@123')
                  setError(null)
                }}
                className="rounded-tile px-3 py-1.5 text-label border border-sf-line bg-sf-surface-2 text-sf-ink-2 hover:border-sf-accent"
              >
                🔧 管理员
              </button>
              <button
                type="button"
                onClick={() => {
                  setUsername('')
                  setPassword('')
                  setError(null)
                }}
                className="rounded-tile px-3 py-1.5 text-label border border-sf-line bg-sf-surface-2 text-sf-ink-2 hover:border-sf-accent"
              >
                🧹 清空输入
              </button>
            </div>
          )}

          <div className="text-center text-[0.75rem] text-sf-ink-2 mt-8">
            StockSignal · 仅供学习与研究所用，不构成投资建议
          </div>
        </div>
      </div>
    </div>
  )
}
