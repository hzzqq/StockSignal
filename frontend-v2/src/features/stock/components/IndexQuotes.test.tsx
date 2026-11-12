// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { IndexQuotes } from './IndexQuotes'

/**
 * 主要指数组件 · 守卫清单（Dashboard.test 仅把本组件 mock 成 () => null，故此处是首次真实覆盖）。
 * 锁定诚实红线：
 *  - current/change/change_pct === null → 显「—」，方向缺失走中性色（不补 0、不臆断跌）。
 *  - 交易屏语义：涨→红(--ss-up) / 跌→绿(--ss-down)，与 report 域相反。
 *  - 四态：loading / error(role=alert) / empty / 有数据。
 *  - note 非空才展示。
 *  - 集成：点击卡片 → 打开 KLineModal 并请求对应指数 K 线。
 */
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => <div data-testid="echart" />,
}))

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }
const ok = (data: unknown) =>
  HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data })

function overrideIndexQuotes(data: unknown) {
  server.use(http.get('/api/v2/read/index-quotes', () => ok(data)))
}

function renderView() {
  return render(
    <Providers>
      <IndexQuotes />
    </Providers>,
  )
}

describe('IndexQuotes · 四态与诚实红线', () => {
  it('加载中 → 显示「加载中…」', async () => {
    // 永不 resolve 的响应把查询锁在 loading 态，验证首帧。
    server.use(http.get('/api/v2/read/index-quotes', () => new Promise<Response>(() => {})))
    renderView()
    expect(await screen.findByText('加载中…', {}, FIND)).toBeTruthy()
  })

  it('取数失败 → role=alert 展示错误信息，不静默空白', async () => {
    server.use(
      http.get(
        '/api/v2/read/index-quotes',
        () =>
          HttpResponse.json(
            { status: 'error', code: 'boom', message: '指数接口 500', data: null },
            { status: 200 },
          ),
      ),
    )
    renderView()
    expect(await screen.findByText('指数接口 500', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('alert')).toBeTruthy()
  })

  it('items 为空数组 → 诚实空态「暂无指数数据」', async () => {
    overrideIndexQuotes({ items: [], note: null })
    renderView()
    expect(await screen.findByText('暂无指数数据', {}, FIND)).toBeTruthy()
  })

  it('成功 → 渲染全部指数卡片，涨红跌绿按交易屏语义', async () => {
    renderView()
    // 默认夹具 5 个指数全部出现
    expect(await screen.findByText('上证指数', {}, FIND)).toBeTruthy()
    expect(screen.getByText('深证成指')).toBeTruthy()
    expect(screen.getByText('创业板指')).toBeTruthy()
    expect(screen.getByText('上证50')).toBeTruthy()
    expect(screen.getByText('沪深300')).toBeTruthy()

    // 上证指数 change=9.7 >0 → 红色(--ss-up)；创业板指 change=-15.6 <0 → 绿色(--ss-down)
    const upBtn = screen.getByLabelText('上证指数 查看 K 线详情')
    const downBtn = screen.getByLabelText('创业板指 查看 K 线详情')
    expect(upBtn.innerHTML).toContain('--color-ss-up')
    expect(downBtn.innerHTML).toContain('--color-ss-down')
  })

  it('current/change/change_pct 为 null → 显「—」且方向走中性色，绝不臆断为跌', async () => {
    overrideIndexQuotes({
      items: [
        {
          code: 'sh000688',
          name: '科创50',
          current: null,
          prev_close: null,
          change: null,
          change_pct: null,
          date: null,
        },
      ],
      note: null,
    })
    renderView()
    const btn = await screen.findByLabelText('科创50 查看 K 线详情', {}, FIND)
    // 现价与涨跌区都应是「—」
    const html = btn.innerHTML
    expect(html).toContain('—')
    // 缺失方向 → 中性色，不得出现涨跌色
    expect(html).toContain('--color-sf-ink-2')
    expect(html).not.toContain('--color-ss-up')
    expect(html).not.toContain('--color-ss-down')
  })

  it('note 非空才展示，且原文呈现', async () => {
    overrideIndexQuotes({ items: [], note: '指数报价样例备注' })
    renderView()
    expect(await screen.findByText('指数报价样例备注', {}, FIND)).toBeTruthy()
  })
})

describe('IndexQuotes · 点击卡片打开 K 线弹窗（集成）', () => {
  it('点击指数卡片 → 弹出 KLineModal 并请求对应指数 K 线', async () => {
    // 默认 index-quotes / index-kline(sh000001) 夹具已就位
    renderView()
    const btn = await screen.findByLabelText('上证指数 查看 K 线详情', {}, FIND)
    fireEvent.click(btn)

    const dialog = await screen.findByRole('dialog', {}, FIND)
    expect(within(dialog).getByText('上证指数')).toBeTruthy()
    expect(within(dialog).getByText(/K 线详情/)).toBeTruthy()
    // K 线组件渲染（EChart 桩）→ 证明 index-kline 已取数且 rows 非空
    expect(await screen.findByTestId('echart', {}, FIND)).toBeTruthy()
    // 关闭按钮存在
    expect(within(dialog).getByLabelText('关闭 K 线弹窗')).toBeTruthy()
  })
})
