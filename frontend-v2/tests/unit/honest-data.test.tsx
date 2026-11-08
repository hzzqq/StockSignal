// @vitest-environment jsdom
import { readFileSync, readdirSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { PositionGauge } from '@/shared/charts/PositionGauge'
import { buildScenarioOption } from '@/shared/charts/ScenarioChart'
import { LoginWelcome } from '@/features/auth/LoginWelcome'
import { MorningReport } from '@/features/morning/MorningReport'
import { GuideView } from '@/features/guide/GuideView'

// GuideView 内含 TanStack <Link>，纯组件渲染需 router context；用最小 <a> 替身，
// 与 w4e/w4f 用例同款做法（不触碰页面实现、不放宽守卫）。
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <a className={className}>{children}</a>
    ),
    useNavigate: () => vi.fn(),
  }
})

/**
 * 诚实红线守卫（批次 5）。
 *
 * 真实缺陷：LoginWelcome 把写死的 5,400+/4,092 当「当前实测」；PositionGauge
 * 用 `pct ?? 0` 在快照缺 position 时伪造「建议空仓 0%」；广度/情景图把缺失
 * 字段画成 0；MorningReport 用机器今天当默认数据日（一进页面就查不存在的笔记）。
 *
 * 守卫采用「剥注释 + 全 src 真扫 + 反例自测」三层，防止注释喂饱或空集恒真。
 */
const ROOT = resolve(process.cwd(), '..')
const SRC = resolve(ROOT, 'frontend-v2/src')

function src(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf8')
}

/** 剥掉块注释与行注释；`(?<!:)` 保留字符串里的 `http://`，避免误删真实代码。 */
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(?<!:)\/\/[^\n]*/g, '')
}

/** 只查「补零伪造数值」与「机器当前时间冒充数据日」两类红线。 */
function findViolations(text: string): string[] {
  const code = stripComments(text)
  const out: string[] = []
  for (const [i, line] of code.split('\n').entries()) {
    if (/\?\?\s*0\b/.test(line)) out.push(`L${i + 1} ?? 0: ${line.trim().slice(0, 100)}`)
    if (/\|\|\s*0\b/.test(line)) out.push(`L${i + 1} || 0: ${line.trim().slice(0, 100)}`)
    // new Date(`${...}T00:00:00Z`) 这类解析固定字符串是合法日期校验，只禁空参构造。
    if (/new Date\(\s*\)/.test(line)) out.push(`L${i + 1} new Date(): ${line.trim().slice(0, 100)}`)
  }
  return out
}

function allSrcFiles(): string[] {
  const out: string[] = []
  function walk(dir: string) {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name)
      if (e.isDirectory()) walk(p)
      else if (/\.(ts|tsx)$/.test(e.name)) out.push(p)
    }
  }
  walk(SRC)
  return out
}

const server = setupServer(...handlers)
let reviewCalls = 0

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
beforeEach(() => { reviewCalls = 0 })
afterEach(() => {
  server.resetHandlers()
  cleanup()
  localStorage.clear()
  vi.restoreAllMocks()
})
afterAll(() => server.close())

describe('守卫自身有效性（反自静音）', () => {
  it('扫描器真的能抓到补零与机器日期，且不被注释/固定日期解析骗过', () => {
    expect(findViolations('const x = a ?? 0\n')).toHaveLength(1)
    expect(findViolations('const x = a || 0\n')).toHaveLength(1)
    expect(findViolations('const d = new Date()\n')).toHaveLength(1)
    expect(findViolations('// 禁止 ?? 0 兜底\nconst ok = 1\n')).toHaveLength(0)
    expect(findViolations('/* 禁止 || 0 */\nconst ok = 1\n')).toHaveLength(0)
    expect(findViolations("const d = new Date(`${s}T00:00:00Z`)\n")).toHaveLength(0)
    expect(findViolations("const url = 'http://127.0.0.1:5050'\n")).toHaveLength(0)
  })

  it('全 src 真扫：文件数与代码量兜底，防止只读了一个文件就宣布通过', () => {
    const files = allSrcFiles()
    expect(files.length).toBeGreaterThanOrEqual(60)
    const total = files.reduce((n, f) => n + stripComments(readFileSync(f, 'utf8')).length, 0)
    expect(total).toBeGreaterThan(50_000)
    const exports = files.reduce(
      (n, f) => n + (stripComments(readFileSync(f, 'utf8')).match(/export (function|const|class|interface|type) /g)?.length ?? 0),
      0,
    )
    expect(exports).toBeGreaterThan(50)
  })
})

describe('全 src 诚实红线', () => {
  it('无任何 ?? 0 / || 0 补零，也无 new Date() 冒充数据日', () => {
    const violations: string[] = []
    for (const f of allSrcFiles()) {
      const rel = f.replace(SRC, 'src').replace(/\\/g, '/')
      for (const v of findViolations(readFileSync(f, 'utf8'))) violations.push(`${rel} ${v}`)
    }
    expect(violations).toEqual([])
  })

  it('登录欢迎页不再把写死数字当实测展示', () => {
    const text = src('frontend-v2/src/features/auth/LoginWelcome.tsx')
    expect(text).not.toMatch(/5,400\+|4,092|3,300\+|4,091/)
    const { container } = render(<LoginWelcome onLogin={() => {}} />)
    expect(container.textContent).toContain('以真实数据为底座')
    expect(container.textContent).not.toMatch(/[\d,]{3,}\+?\s*(条|日)/)
  })

  it('引导阶段就应用密度偏好（登录页不在 AppShell 下）', () => {
    const code = stripComments(src('frontend-v2/src/main.tsx'))
    expect(code).toContain('applyPreferences()')
    expect(code).toContain("from '@/lib/preferences'")
  })

  it('设置页把两个真实开关都说清楚，不留下不存在的变量名', () => {
    const text = src('frontend-v2/src/features/settings/SettingsView.tsx')
    expect(text).toContain('STOCKSIGNAL_USE_MOCKS=1')
    expect(text).toContain('VITE_ENABLE_MOCKS=false')
  })
})

describe('真实渲染行为', () => {
  it('仓位缺失 → 「—」空态，绝不显示 0%', () => {
    render(<PositionGauge pct={null} />)
    expect(screen.getByRole('status', { name: '暂无仓位建议数据' })).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
    expect(screen.queryByText('0%')).toBeNull()
  })

  it('仓位有值 → 不再显示空态（组件真的分了两态）', () => {
    render(<PositionGauge pct={55} />)
    expect(screen.queryByRole('status', { name: '暂无仓位建议数据' })).toBeNull()
  })

  it('情景概率缺失 → 数据点为 null，不是 0', () => {
    for (const items of [
      [{ name: '乐观', prob: null }],
      [{ name: '中性' }],
      [{ name: '悲观', prob: 0 }],
    ]) {
      const option = buildScenarioOption(items) as unknown as {
        series: { data: { value: unknown }[] }[]
      }
      const values = option.series[0].data.map((d) => d.value)
      if (items[0].name === '悲观') expect(values[0]).toBe(0) // 真实 0 保留，不误伤
      else expect(values[0]).toBeNull()
      expect(values[0]).not.toBeUndefined()
    }
  })

  it('晨报首帧不发请求，选了日期才查，且不预填机器今天', () => {
    server.use(http.get('/api/v2/read/review-notes', () => {
      reviewCalls += 1
      return HttpResponse.json({
        status: 'ok', code: 'ok', message: 'ok',
        data: { date: '2026-09-21', content: '复盘笔记正文' },
      })
    }))
    render(<Providers><MorningReport /></Providers>)
    const input = document.querySelector('input[type="date"]') as HTMLInputElement
    expect(input).toBeTruthy()
    expect(input.value).toBe('')
    expect(screen.getByText(/未选择日期，不发起查询/)).toBeTruthy()
    expect(reviewCalls).toBe(0)

    fireEvent.change(input, { target: { value: '2026-09-21' } })
    return waitFor(() => expect(reviewCalls).toBe(1), { timeout: 5000 })
      .then(() => waitFor(() => expect(screen.getByText('复盘笔记正文')).toBeTruthy(), { timeout: 5000 }))
  })

  it('新手教程写入 localStorage 被禁用时不崩溃，进度仍在本会话生效', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    render(<GuideView />)
    const bar = screen.getByRole('progressbar', { name: '上手进度' })
    expect(() => fireEvent.click(screen.getByRole('checkbox', { name: '看一遍今日决策面板' }))).not.toThrow()
    expect(bar.getAttribute('aria-valuenow')).toBe('25')
  })
})
