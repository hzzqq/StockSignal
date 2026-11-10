import { useState, type FormEvent } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { login } from '@/api/endpoints'
import { clearAuth } from '@/app/guards'
import { NAV, UTILITY_PATHS } from '@/nav/nav'
import { getDailySnapshot } from '@/api/read'
import { useQuery } from '@tanstack/react-query'
import { LoginWelcome } from './LoginWelcome'

/**
 * 登录页（沿用第一版 v1 的双态设计）。
 *
 * 两态（老板 2026-11-08 拍板「欢迎页 + 分栏两态都要」）：
 *   1. **欢迎态**：v1 `modules/session.py::_render_login_gate()` 的品牌门禁页
 *      （Hero 渐变大标题 + 品牌卡 + 演示账号徽章 + 渐变主按钮 + 脚注）。
 *      → 见 `LoginWelcome.tsx`。
 *   2. **登录态**：v1 `pages/90_登录.py` 的「左行情台 ｜ 右表单」分栏。
 *      左栏 = 资金温度仪表 + 今日市场涨跌 + AI 信号（数据取 v2 已有
 *      `GET /api/v2/read/daily-snapshot`，零网络优先、缺失如实显「—」）；
 *      右栏 = 用户名/密码表单 + 演示账号一键填充。
 *
 * 与 v1 的差异（有意为之）：
 *   - v1 有「验证码登录 / 注册」两个 Tab。验证码依赖短信网关，v2 **不做假功能**
 *     （与 v1 诚实红线一致：未接入即标注不可用，而非留个假按钮）。
 *   - v1 用 Streamlit 注入 HTML；v2 是 React + Tailwind + 语义令牌。
 *
 * 缺陷修复（本轮附带）：
 *   - `KNOWN_PATHS` 原本是手抄 nav.ts 的 9 条子集，漏掉 W3/W4 新增的 9 条路径
 *     → 未登录访问 `/stock/research` 等页时，登录后被静默甩回首页。
 *     现改为**从 NAV 派生**（单一真理源，不再手抄），永不漏。
 *   - 表单可访问性：输入框补 `<label>`、`autoComplete`、`name`；错误提示用
 *     `aria-invalid` + `aria-describedby` 与输入框关联（原先只有 placeholder，
 *     读屏器念不出字段名）。
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
      // 持久化当前用户（含角色），供导航与页面门控；MSW 缺 user 时不报错。
      if (result.user) localStorage.setItem('ss_user', JSON.stringify(result.user))
      // 保留来源路由：登录后回到触发登录的页面（from 由守卫写入 search）
      navigate({ to: from as '/' })
    } catch (err) {
      clearAuth()
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  if (stage === 'welcome') {
    return <LoginWelcome onLogin={() => setStage('form')} />
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-sf-bg px-6 py-10 text-sf-ink">
      <div className="w-full max-w-[980px] grid grid-cols-1 md:grid-cols-[0.46fr_0.54fr] gap-8">
        {/* ── 左栏：今日市场实时变化（v1 行情台，v2 令牌化） ── */}
        <MarketDesk />

        {/* ── 右栏：登录表单 ── */}
        <div className="max-w-[420px] w-full mx-auto">
          <div className="text-center mb-6">
            <h1 className="text-[2.2rem] font-black leading-tight mb-1.5">
              🔑 登录 StockSignal
            </h1>
            <p className="text-[0.95rem] text-sf-ink-2 m-0">
              登录后解锁行情看板、个股分析、形态选股等全部功能
            </p>
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
                placeholder="请输入用户名"
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
                autoComplete="current-password"
                className="w-full px-3 py-2 rounded-tile bg-sf-surface-2 border border-sf-line outline-none focus:border-sf-accent"
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'login-error' : undefined}
              />
            </div>

            {error && (
              <p id="login-error" role="alert" className="text-sf-danger text-body">
                {error}
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
              {loading ? '登录中…' : '立即登录'}
            </button>
          </form>

          {/* 演示账号一键填充（v1 同款，快捷入口） */}
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

          <div className="text-center text-[0.75rem] text-sf-ink-2 mt-8">
            StockSignal · 仅供学习与研究所用，不构成投资建议
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * 左栏行情台：资金温度 + 今日市场涨跌 + AI 信号。
 *
 * 数据源：v2 已有 `GET /api/v2/read/daily-snapshot`（今日快照，单一真理源）。
 * 诚实红线：
 *   - 端点需鉴权，未登录时取不到 → 全部显示「—」，**不编造任何数字**；
 *   - 涨跌配色用交易屏语义（涨红跌绿）：`--color-ss-up` / `--color-ss-down`；
 *   - 温度缺失显示「—」，进度条宽度取 0，不虚构。
 */
function MarketDesk() {
  const { data } = useQuery({
    queryKey: ['read', 'daily-snapshot'],
    queryFn: getDailySnapshot,
    retry: false,
  })

  const ind = (data?.indicators ?? {}) as Record<string, unknown>
  const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null

  const temperature = num(data?.temperature)
  const up = num(ind.up_count)
  const down = num(ind.down_count)
  const limitUp = num(ind.limit_up)
  const limitDown = num(ind.limit_down)
  const redRatio = num(ind.red_ratio)
  const medianChg = num(ind.median_chg)
  const ef = data?.event_factor
  const longCount = num(ef?.long_count)
  const efAdj = num(ef?.adj)
  const efAsOf = ef?.as_of

  const tempWidth = temperature == null ? 0 : Math.max(0, Math.min(100, temperature))
  const dash = '—'

  return (
    <div className="space-y-4">
      {/* 品牌区 */}
      <div className="rounded-card bg-sf-surface border border-sf-line p-5">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-3xl" aria-hidden="true">
            📊
          </span>
          <div>
            <div className="text-[1.25rem] font-extrabold text-sf-ink">StockSignal</div>
            <div className="text-label text-sf-ink-3">A股事件驱动投资分析平台</div>
          </div>
        </div>
        <p className="text-[0.86rem] text-sf-ink-2 leading-relaxed m-0">
          事件驱动的选股与仓位决策闭环：情绪温度 → 事件因子 → 仓位建议，逐日回测实证。
        </p>
      </div>

      {/* 资金温度 */}
      <div className="rounded-card bg-sf-surface border border-sf-line p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-title font-medium text-sf-ink-2">资金温度</span>
          <span
            className="text-label font-semibold rounded-full px-2 py-0.5"
            style={{
              background: 'color-mix(in srgb, var(--color-brand-1) 12%, transparent)',
              color: 'var(--color-brand-1)',
              border: '1px solid color-mix(in srgb, var(--color-brand-1) 30%, transparent)',
            }}
          >
            {data?.cycle ?? '快照'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div
            className="text-[2rem] font-black tabular-nums min-w-[62px] text-center"
            style={{ color: 'var(--color-brand-1)' }}
          >
            {temperature == null ? dash : Math.round(temperature)}
          </div>
          <div
            className="flex-1 h-2.5 rounded-full overflow-hidden"
            style={{ background: 'color-mix(in srgb, var(--color-brand-1) 14%, var(--color-sf-line))' }}
            role="img"
            aria-label={
              temperature == null ? '资金温度暂无数据' : `资金温度 ${Math.round(temperature)} / 100`
            }
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${tempWidth}%`,
                background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))',
              }}
            />
          </div>
        </div>
        <div className="text-label text-sf-ink-3 mt-2">
          快照数据日：{data?.date ?? dash}
          {data?.as_of && data.as_of !== data.date ? ` · 生成于 ${data.as_of}` : ''}
        </div>
      </div>

      {/* 今日市场 */}
      <div className="rounded-card bg-sf-surface border border-sf-line p-5">
        <div className="text-title font-medium text-sf-ink-2 mb-3">今日市场</div>
        <div className="grid grid-cols-2 gap-3">
          <DeskMetric label="上涨家数" value={up} color="var(--color-ss-up)" dash={dash} />
          <DeskMetric label="下跌家数" value={down} color="var(--color-ss-down)" dash={dash} />
          <DeskMetric label="涨停" value={limitUp} color="var(--color-ss-up)" dash={dash} />
          <DeskMetric label="跌停" value={limitDown} color="var(--color-ss-down)" dash={dash} />
        </div>
        <div className="text-label text-sf-ink-3 mt-3 leading-relaxed">
          红盘占比 {redRatio == null ? dash : `${redRatio.toFixed(1)}%`} · 个股中位涨幅{' '}
          {medianChg == null ? dash : `${medianChg >= 0 ? '+' : ''}${medianChg.toFixed(2)}%`}
        </div>
      </div>

      {/* AI 信号 */}
      <div className="rounded-card bg-sf-surface border border-sf-line p-5">
        <div className="text-title font-medium text-sf-ink-2 mb-2">AI 信号</div>
        <div className="text-[0.86rem] text-sf-ink mb-1">
          看多标的 <b style={{ color: 'var(--color-brand-1)' }}>{longCount ?? dash}</b> 只
          {efAdj != null ? <> · 调整分 {efAdj}</> : null}
        </div>
        <div className="text-label text-sf-ink-3">
          {efAsOf ? `信号数据日 ${efAsOf}` : '事件因子信号暂无数据'}
        </div>
      </div>
    </div>
  )
}

/** 行情台单指标：数值用等宽数字，缺失显示「—」并显式标注（不补 0）。 */
function DeskMetric({
  label,
  value,
  color,
  dash,
}: {
  label: string
  value: number | null
  color: string
  dash: string
}) {
  return (
    <div>
      <div className="text-label text-sf-ink-3">{label}</div>
      <div className="text-[1.4rem] font-bold tabular-nums" style={{ color }}>
        {value == null ? dash : value}
      </div>
    </div>
  )
}
