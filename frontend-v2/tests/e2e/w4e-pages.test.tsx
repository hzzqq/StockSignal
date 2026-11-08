// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { ProjectIntro } from '@/features/dashboard/ProjectIntro'
import { CatalogView } from '@/features/catalog/CatalogView'
import { DataSourceView } from '@/features/catalog/DataSourceView'
import { SettingsView } from '@/features/settings/SettingsView'
import { V1_PAGES, V1_PAGES_TOTAL } from '@/features/catalog/v1Pages.generated'
import { mappingOf, statusCounts } from '@/features/catalog/v2Mapping'
import { getDensity, getV1Base, setV1Base, v1PageUrl, applyPreferences } from '@/lib/preferences'
import { NAV } from '@/nav/nav'

/**
 * W4-E · 设置 / v1 功能全景 / 只读数据浏览器 / v1 首页 Hero 的真实回归。
 *
 * 照 w4b-pages 的惯例：用 <Providers> 独立渲染纯组件，TanStack <Link> 以最小
 * <a> 替身替换（不触碰页面实现、不放宽守卫）。网络一律走 MSW node，零真实请求。
 */
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

const ROOT = resolve(process.cwd(), '..')  // vitest cwd = frontend-v2
const server = setupServer(
  ...handlers,
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  localStorage.clear()
  delete document.documentElement.dataset.density
})
afterAll(() => server.close())

function mount(node: ReactNode) {
  return render(<Providers>{node}</Providers>)
}

describe('W4-E · v1 首页 Hero（1:1 移植）', () => {
  it('眉标 / 痛点大标题 / 三张编号卡 / 金句 / 三色能力卡全部落地', () => {
    mount(<ProjectIntro />)
    expect(screen.getByText(/A股事件驱动 · 决策闭环/)).toBeTruthy()
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.textContent).toContain('看了一堆分析，最后还是')
    expect(h1.textContent).toContain('凭感觉')
    expect(h1.textContent).toContain('下单')
    expect(screen.getByText('当初为什么买？')).toBeTruthy()
    expect(screen.getByText('赚了，是判断对还是运气？')).toBeTruthy()
    expect(screen.getByText('亏了，错在哪一步？')).toBeTruthy()
    expect(screen.getByText('情绪温度计')).toBeTruthy()
    expect(screen.getByText('事件驱动信号')).toBeTruthy()
    expect(screen.getByText('决策闭环回测')).toBeTruthy()
    expect(screen.getByText(/问题不在信息不够/)).toBeTruthy()
  })

  it('Hero 不照抄 v1 历史数字（文案里不得出现旧测试数 / 旧回测日数）', () => {
    const { container } = mount(<ProjectIntro />)
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/3,300\+|4,091|3,197|92 个 REST/)
  })

  it('Dashboard 真实挂载 Hero（源码契约，防止只建组件不接线）', () => {
    const src = readFileSync(resolve(ROOT, 'frontend-v2/src/features/dashboard/Dashboard.tsx'), 'utf8')
    expect(src).toContain("import { ProjectIntro } from './ProjectIntro'")
    expect(src).toContain('<ProjectIntro />')
  })
})

describe('W4-E · v1 功能全景清单（真实性）', () => {
  it('总数 = 清单长度，每条都有真实文件名与 v1 相对 URL', () => {
    expect(V1_PAGES_TOTAL).toBe(V1_PAGES.length)
    expect(V1_PAGES_TOTAL).toBeGreaterThan(60)
    for (const p of V1_PAGES) {
      expect(p.file).toMatch(/^\d{2}_.+\.py$/)
      expect(p.v1Url).toBe('/' + p.file.replace(/\.py$/, ''))
      expect(p.group.length).toBeGreaterThan(0)
    }
  })

  it('三档状态数量之和 = 总数，且状态互斥', () => {
    const c = statusCounts()
    expect(c.native + c.data + c['v1-only']).toBe(V1_PAGES_TOTAL)
    expect(c.native).toBeGreaterThan(10)
    expect(c['v1-only']).toBeGreaterThan(0)
    for (const p of V1_PAGES) {
      const m = mappingOf(p)
      if (m.status === 'native') expect(m.to).toBeTruthy()
      if (m.status === 'data') expect(m.dataPath).toMatch(/^\/api\/v2\/read\//)
      if (m.status === 'v1-only') {
        expect(m.to).toBeUndefined()
        expect(m.dataPath).toBeUndefined()
      }
    }
  })

  it('native 目标都在 AppPath 内（不许指向不存在的路由）', () => {
    // AppPath 是类型，运行时用 NAV + 新增三条侧边栏路径做白名单校验
    const known = new Set<string>([
      ...NAV.flatMap((g) => g.items.map((i) => i.to)),
      '/settings', '/catalog', '/data',
    ])
    for (const p of V1_PAGES) {
      const m = mappingOf(p)
      if (m.status === 'native' && m.to) expect(known.has(m.to)).toBe(true)
    }
  })
})

describe('W4-E · 功能全景页交互', () => {
  it('如实展示三档统计与「列出 ≠ 已实现」声明', () => {
    mount(<CatalogView />)
    expect(screen.getByRole('heading', { name: 'v1 功能全景' })).toBeTruthy()
    expect(screen.getAllByText(String(V1_PAGES_TOTAL)).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/列出 ≠ 已实现/)).toBeTruthy()
    expect(screen.getAllByText(String(statusCounts().native)).length).toBeGreaterThanOrEqual(1)
  })

  it('搜索与状态筛选真实生效，不重复计数', () => {
    mount(<CatalogView />)
    const input = screen.getByRole('searchbox', { name: '搜索功能' })
    fireEvent.change(input, { target: { value: '温度计' } })
    expect(screen.getByText(/当前显示 1 项/)).toBeTruthy()
    expect(screen.getByText('市场温度计')).toBeTruthy()
    expect(screen.queryByText('行情看板')).toBeNull()

    fireEvent.change(input, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: '仅 v1' }))
    const label = screen.getByText(/当前显示 \d+ 项/).textContent ?? ''
    const shown = Number(label.match(/\d+/)?.[0] ?? 0)
    expect(shown).toBe(statusCounts()['v1-only'])
  })

  it('「仅 v1」项给 v1 直达链接且编码中文页名', () => {
    const target = V1_PAGES.find((p) => mappingOf(p).status === 'v1-only')
    expect(target).toBeTruthy()
    if (!target) return
    const url = v1PageUrl(target.v1Url)
    expect(url).toContain('http://127.0.0.1:8501/')
    expect(url).not.toContain(target.name) // 中文已编码
  })
})

describe('W4-E · 设置页（真实生效）', () => {
  it('数据源模式如实显示，连通性检测记录真实 HTTP 与耗时', async () => {
    mount(<SettingsView />)
    expect(screen.getByText('开发模拟数据（MSW）')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '测试连通性' }))
    await waitFor(() => expect(screen.getByText(/HTTP 200/)).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/MSW 模拟响应（非真实后端）/)).toBeTruthy()
    expect(screen.queryByText(/后端健康检查通过/)).toBeNull()
  })

  it('密度切换真实写入 localStorage 与 document.dataset，不是摆设', () => {
    mount(<SettingsView />)
    fireEvent.click(screen.getByRole('radio', { name: '紧凑' }))
    expect(getDensity()).toBe('compact')
    expect(document.documentElement.dataset.density).toBe('compact')
    fireEvent.click(screen.getByRole('radio', { name: '标准' }))
    expect(getDensity()).toBe('comfortable')
    expect(document.documentElement.dataset.density).toBe('comfortable')
    applyPreferences()
    expect(document.documentElement.dataset.density).toBe('comfortable')
  })

  it('v1 地址保存后直达链接立即使用新地址', () => {
    mount(<SettingsView />)
    const input = screen.getByRole('textbox', { name: 'v1 服务地址' })
    fireEvent.change(input, { target: { value: 'http://127.0.0.1:8600/' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(getV1Base()).toBe('http://127.0.0.1:8600')
    expect(v1PageUrl('/10_行情看板')).toContain('http://127.0.0.1:8600/')
    setV1Base('http://127.0.0.1:8501')
  })

  it('侧边栏底部固定设置与功能全景入口，且 NAV 仍 4 组 / 图标唯一', () => {
    const src = readFileSync(resolve(ROOT, 'frontend-v2/src/app/AppShell.tsx'), 'utf8')
    expect(src).toContain('to="/settings"')
    expect(src).toContain('to="/catalog"')
    expect(src).toContain('applyPreferences()')
    const items = NAV.flatMap((g) => g.items)
    expect(NAV.length).toBe(4)
    expect(new Set(items.map((i) => i.icon)).size).toBe(items.length)
  })

  it('启动脚本默认连真实后端（MSW off），并允许显式覆盖回 Mock', () => {
    const bat = readFileSync(resolve(ROOT, 'start_frontend_v2.bat'), 'utf8')
    const sh = readFileSync(resolve(ROOT, 'start_frontend_v2.sh'), 'utf8')
    expect(bat).toContain('set "VITE_ENABLE_MOCKS=false"')
    expect(bat).toContain('STOCKSIGNAL_USE_MOCKS')
    expect(sh).toContain('export VITE_ENABLE_MOCKS=false')
    expect(sh).toContain('STOCKSIGNAL_USE_MOCKS')
  })

  it('启动脚本后台常驻：关闭命令行窗口后服务仍在', () => {
    const bat = readFileSync(resolve(ROOT, 'start_frontend_v2.bat'), 'utf8')
    const stop = readFileSync(resolve(ROOT, '_stop_services.bat'), 'utf8')
    const py = readFileSync(resolve(ROOT, 'scripts/start_v2_detached.py'), 'utf8')
    // 注释与 echo 提示文案不是行为证据，只检查可执行行
    const code = bat.split(/\r?\n/).filter((l) => {
      const s = l.trim().toLowerCase()
      return s && !s.startsWith('rem ') && !s.startsWith('::') && !s.startsWith('echo') && !s.startsWith('@echo')
    }).join('\n')
    expect(code).toContain('scripts\\start_v2_detached.py')
    expect(code).toContain('start_frontend_v2_hidden.vbs')
    expect(code).toContain('wscript.exe //nologo')
    expect(code).toContain('"--worker"')
    expect(code).toContain('-p tcp')
    expect(code).toContain('LISTENING')
    expect(code).not.toMatch(/^start\s+"StockSignal/m)
    expect(stop).toContain('active_ports_v2.json')
    expect(stop).toContain('-p tcp')
    expect(py).toContain('CREATE_NO_WINDOW')
    expect(py).toContain('CREATE_NEW_PROCESS_GROUP')
    expect(py).toContain('start_new_session')
    expect(py).toContain('SingleInstance')
  })
})

describe('W4-E · 只读端点数据浏览器', () => {
  it('端点清单来自后端枚举，选中后展示真实信封数据、不编造行', async () => {
    mount(<DataSourceView />)
    // fixture 12 个端点中 1 个含路径参数被排除，其余 11 个可查看（需参端点带示例参数）
    expect(await screen.findByText(/共 11 个可查看端点/)).toBeTruthy()
    expect(screen.queryByText('响应不是合法 JSON 信封')).toBeNull()
    const select = screen.getByRole('combobox', { name: '只读端点' })
    fireEvent.change(select, { target: { value: '/api/v2/read/index-quotes' } })
    await waitFor(() => expect(screen.getByText('items')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/HTTP 200/)).toBeTruthy()
    expect(screen.getByText(/信封 ok/)).toBeTruthy()
    // 需参端点选中后自动填入示例参数，并真实 GET 成功（不再是 400 假故障）
    fireEvent.change(select, { target: { value: '/api/v2/read/six-dim' } })
    await waitFor(() => expect(
      (screen.getByRole('textbox', { name: '查询参数' }) as HTMLInputElement).value,
    ).toBe('code=600519'), { timeout: 5000 })
    expect(screen.getByText(/当前端点需参数，已填示例值/)).toBeTruthy()
  })

  it('Mock 态明确标注结果为模拟响应', () => {
    mount(<DataSourceView />)
    expect(screen.getByText(/当前为开发 Mock 环境/)).toBeTruthy()
  })
})
