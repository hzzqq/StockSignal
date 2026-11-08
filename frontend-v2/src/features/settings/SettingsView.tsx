import { useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { clearAuth } from '@/app/guards'
import { mocksEnabled } from '@/api/diagnostics'
import { getDensity, getV1Base, setDensity, setV1Base, type Density } from '@/lib/preferences'
import { V1_PAGES_TOTAL } from '@/features/catalog/v1Pages.generated'
import { ThemeToggle } from '@/shared/ui/ThemeToggle'
import { Card } from '@/shared/ui/Card'

/**
 * 设置（/settings）：侧边栏底部固定入口，全部为**真实生效**的本地设置。
 *
 * 诚实口径：
 *  - 偏好只存浏览器 localStorage，不写后端，也不谎称同步到账号；
 *  - 连通性检测发一次真实 GET /api/health，HTTP 状态与耗时如实显示，失败不包装成成功；
 *  - 数据源模式直接读运行时开关，不猜测；MSW 态明确标注结果为模拟数据；
 *  - 本前端只保存 token，不缓存用户名 —— 不编造账户信息。
 */
const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'
// 健康检测硬超时：后端不响应时不能让按钮永远停在「检测中…」。
const HEALTH_TIMEOUT_MS = 5000

interface HealthResult {
  httpStatus: number | null
  latencyMs: number
  detail: string
  simulated: boolean
}

export function SettingsView() {
  const navigate = useNavigate()
  const [density, setDensityState] = useState<Density>(getDensity)
  const [v1Base, setV1BaseState] = useState(getV1Base)
  const [savedV1, setSavedV1] = useState(false)
  const [health, setHealth] = useState<HealthResult | null>(null)
  const [testing, setTesting] = useState(false)
  const mocked = mocksEnabled()

  function changeDensity(value: Density) {
    setDensity(value)
    setDensityState(getDensity())
  }

  function saveV1Base() {
    setV1Base(v1Base)
    setV1BaseState(getV1Base())
    setSavedV1(true)
  }

  async function testBackend() {
    setTesting(true)
    const started = performance.now()
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS)
    try {
      const res = await fetch(`${BASE}/health`, {
        method: 'GET', credentials: 'include', signal: controller.signal,
      })
      setHealth({
        httpStatus: res.status,
        latencyMs: Math.round(performance.now() - started),
        detail: mocked
          ? (res.ok ? 'MSW 模拟响应（非真实后端）' : `模拟响应返回 HTTP ${res.status}`)
          : (res.ok ? '后端健康检查通过' : `健康检查返回 HTTP ${res.status}`),
        simulated: mocked,
      })
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === 'AbortError'
      setHealth({
        httpStatus: null,
        latencyMs: Math.round(performance.now() - started),
        detail: aborted
          ? `检测超时（>${HEALTH_TIMEOUT_MS}ms），后端未响应`
          : `无法连接：${err instanceof Error ? err.message : String(err)}`,
        simulated: mocked,
      })
    } finally {
      clearTimeout(timer)
      setTesting(false)
    }
  }

  function onLogout() {
    clearAuth()
    navigate({ to: '/login', search: { from: '/' } })
  }

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">设置</h2>
        <span className="text-label text-sf-ink-3">本机偏好 · 保存在此浏览器</span>
      </div>

      <Card title="外观">
        <div className="flow">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-body text-sf-ink-2 w-24 shrink-0">主题</span>
            <ThemeToggle />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-body text-sf-ink-2 w-24 shrink-0">表格密度</span>
            <div role="radiogroup" aria-label="表格密度" className="flex items-center gap-1">
              {(['comfortable', 'compact'] as Density[]).map((d) => (
                <button
                  key={d}
                  type="button"
                  role="radio"
                  aria-checked={density === d}
                  onClick={() => changeDensity(d)}
                  className={[
                    'px-2 py-1 rounded-tile text-label border transition-colors',
                    density === d ? 'text-sf-ink border-sf-accent bg-sf-surface-2' : 'text-sf-ink-2 border-sf-line',
                  ].join(' ')}
                >
                  {d === 'compact' ? '紧凑' : '标准'}
                </button>
              ))}
            </div>
            <span className="text-label text-sf-ink-3">
              作用于功能全景 / 数据浏览器的表格行距（{density === 'compact' ? '紧凑' : '标准'}）
            </span>
          </div>
        </div>
      </Card>

      <Card title="数据源与连接">
        <div className="flow">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-body text-sf-ink-2 w-24 shrink-0">当前模式</span>
            <span className={mocked ? 'text-body text-sf-warn' : 'text-body text-sf-ok'}>
              {mocked ? '开发模拟数据（MSW）' : '真实后端'}
            </span>
            <span className="text-label text-sf-ink-3">
              {mocked
                ? '页面上的行情与检测结果可能是模拟响应，不代表真实数据'
                : '请求经 Vite 代理发往后端，数据来自真实本地数据源'}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-body text-sf-ink-2 w-24 shrink-0">API 地址</span>
            <code className="text-label font-mono text-sf-ink">{BASE}</code>
            <button
              type="button"
              onClick={() => void testBackend()}
              disabled={testing}
              className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-label text-sf-ink hover:border-sf-accent disabled:opacity-50"
            >
              {testing ? '检测中…' : '测试连通性'}
            </button>
            {health ? (
              <span role="status" className={!health.simulated && health.httpStatus !== null && health.httpStatus < 400 ? 'text-label text-sf-ok' : 'text-label text-sf-warn'}>
                HTTP {health.httpStatus ?? '—'} · {health.latencyMs} ms · {health.detail}
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex flex-wrap items-center gap-3">
              <span className="text-body text-sf-ink-2 w-24 shrink-0">v1 服务地址</span>
              <input
                type="url"
                aria-label="v1 服务地址"
                value={v1Base}
                onChange={(e) => { setV1BaseState(e.target.value); setSavedV1(false) }}
                className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
              />
            </label>
            <button
              type="button"
              onClick={saveV1Base}
              className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-label text-sf-ink hover:border-sf-accent"
            >
              保存
            </button>
            {savedV1 ? <span role="status" className="text-label text-sf-ok">已保存：{v1Base}</span> : null}
            <span className="text-label text-sf-ink-3">用于「仅 v1」功能的直达链接</span>
          </div>
        </div>
      </Card>

      <Card title="账户">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-label text-sf-ink-3">
            本前端只保存登录 token、不缓存用户名；如需切换账号请退出后重新登录。
          </span>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-label text-sf-ink hover:border-sf-accent"
          >
            退出登录
          </button>
        </div>
      </Card>

      <Card title="关于与语义">
        <div className="flow text-body text-sf-ink-2">
          <p className="m-0">构建模式：<code className="font-mono">{String(import.meta.env.MODE)}</code></p>
          <p className="m-0">v1 功能页登记数：<strong className="text-sf-ink">{V1_PAGES_TOTAL}</strong>（磁盘实扫，见功能全景）</p>
          <p className="m-0">
            价格配色：交易屏{' '}
            <span style={{ color: 'var(--color-ss-up)' }}>涨=红</span> /{' '}
            <span style={{ color: 'var(--color-ss-down)' }}>跌=绿</span>；
            报告与个股页为绿涨红跌；状态灯用独立状态色，不混用涨跌色。
          </p>
          <p className="m-0 text-label text-sf-ink-3">
            提示：用 start_frontend_v2.bat / .sh 启动时默认连接真实后端；需要演示数据可设 STOCKSIGNAL_USE_MOCKS=1。
          </p>
        </div>
      </Card>

      <Card title="快捷入口">
        <div className="flex flex-wrap gap-4 text-body">
          <Link to="/catalog" className="text-sf-accent hover:underline">v1 功能全景</Link>
          <Link to="/data" className="text-sf-accent hover:underline">只读端点数据浏览器</Link>
          <Link to="/diagnostics" className="text-sf-accent hover:underline">数据源与接口检测</Link>
          <Link to="/" className="text-sf-accent hover:underline">返回首页</Link>
        </div>
      </Card>
    </div>
  )
}
