// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { klineFull } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { KLineModal } from './KLineModal'

/**
 * K 线弹窗 · 守卫清单（此前无独立测试，Dashboard.test 只把 IndexQuotes 整体 mock）。
 * 锁定：
 *  - open=false / code=null → 不渲染（无 dialog），且不发请求。
 *  - open=true + 合法 code → 弹 dialog；title = name ?? code。
 *  - 关闭三件套：关闭按钮 / Esc / 点遮罩 → 均触发 onClose。
 *  - 取数失败 → role=alert 展示错误；rows 空 → 诚实空态。
 *  - note 非空才展示。
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

function renderModal(opts: {
  open?: boolean
  code?: string | null
  name?: string
  onClose?: () => void
}) {
  const onClose = opts.onClose ?? vi.fn()
  const utils = render(
    <Providers>
      <KLineModal
        open={opts.open ?? true}
        code={opts.code ?? null}
        name={opts.name}
        priceDomain="market"
        onClose={onClose}
      />
    </Providers>,
  )
  return { onClose, ...utils }
}

describe('KLineModal · 渲染门控与标题', () => {
  it('open=false → 不渲染 dialog，且不发 K 线请求', async () => {
    const reqs: string[] = []
    server.use(
      http.get('/api/v2/read/stock-kline', ({ request }) => {
        reqs.push(new URL(request.url).searchParams.get('code') ?? '')
        return ok(klineFull)
      }),
    )
    renderModal({ open: false, code: '000001' })
    expect(screen.queryByRole('dialog')).toBeNull()
    // 未挂载即 return null，hook 虽调用但 enabled 拦截，不应触达 resolver
    expect(reqs).toHaveLength(0)
  })

  it('open=true + name → 弹窗标题为 name，K 线组件渲染', async () => {
    const { onClose } = renderModal({ open: true, code: '000001', name: '上证指数' })
    expect(await screen.findByRole('dialog', {}, FIND)).toBeTruthy()
    expect(screen.getByText('上证指数')).toBeTruthy()
    expect(screen.getByText(/K 线详情/)).toBeTruthy()
    expect(await screen.findByTestId('echart', {}, FIND)).toBeTruthy()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('open=true + 无 name → 标题回落为 code', async () => {
    renderModal({ open: true, code: '000001' })
    expect(await screen.findByLabelText('000001 K 线详情', {}, FIND)).toBeTruthy()
  })
})

describe('KLineModal · 关闭三件套', () => {
  it('点击「关闭」按钮 → onClose 调用一次', async () => {
    const { onClose } = renderModal({ open: true, code: '000001', name: '上证指数' })
    const closeBtn = await screen.findByLabelText('关闭 K 线弹窗', {}, FIND)
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('按 Esc → onClose 调用一次', async () => {
    const { onClose } = renderModal({ open: true, code: '000001', name: '上证指数' })
    await screen.findByRole('dialog', {}, FIND)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('点击遮罩（非弹窗内部）→ onClose 调用一次', async () => {
    const { onClose } = renderModal({ open: true, code: '000001', name: '上证指数' })
    await screen.findByRole('dialog', {}, FIND)
    fireEvent.click(screen.getByRole('presentation'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('KLineModal · 诚实四态', () => {
  it('取数失败 → role=alert 展示错误，不静默空白', async () => {
    server.use(
      http.get(
        '/api/v2/read/stock-kline',
        () =>
          HttpResponse.json(
            { status: 'error', code: 'boom', message: 'K 线接口 500', data: null },
            { status: 200 },
          ),
      ),
    )
    renderModal({ open: true, code: '000001', name: '上证指数' })
    expect(await screen.findByText('K 线接口 500', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('alert')).toBeTruthy()
  })

  it('rows 空数组 → 诚实空态「暂无 K 线数据」（000003 夹具）', async () => {
    renderModal({ open: true, code: '000003', name: '示例' })
    expect(await screen.findByText('暂无 K 线数据', {}, FIND)).toBeTruthy()
  })

  it('note 非空才展示，且原文呈现', async () => {
    server.use(
      http.get(
        '/api/v2/read/stock-kline',
        () => ok({ ...klineFull, note: 'K 线样例备注' }),
      ),
    )
    renderModal({ open: true, code: '000001', name: '上证指数' })
    expect(await screen.findByText('K 线样例备注', {}, FIND)).toBeTruthy()
  })
})
