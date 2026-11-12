import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DataExport } from './DataExport'
import { ApiError } from '@/api/client'
import type { DailySnapshot } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getSnapshotDates: vi.fn(),
  getSnapshotByDate: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
import { getSnapshotDates, getSnapshotByDate } from '@/api/read'
const datesMock = vi.mocked(getSnapshotDates)
const snapMock = vi.mocked(getSnapshotByDate)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = { date: '2026-03-01', temperature: 55.5 } as DailySnapshot

beforeEach(() => {
  datesMock.mockReset().mockResolvedValue(['2026-03-01', '2026-02-28'])
  snapMock.mockReset().mockResolvedValue(okData)
})

/** 选中日期（先等下拉清单落定再触发 change，避开 act 时序抖动）。 */
async function pickDate(date: string) {
  await screen.findByText('2026-02-28')
  fireEvent.change(screen.getByRole('combobox'), { target: { value: date } })
}

describe('DataExport · 95 数据导出 · 归档快照 + 错误按 code 分流', () => {
  it('默认未选日期 → 不发快照查询（enabled 守卫），列出归档日期', async () => {
    renderWithClient(<DataExport />)
    expect(screen.getByText('— 请选择 —')).toBeTruthy()
    await expect(screen.findByText('2026-02-28')).resolves.toBeTruthy()
    expect(snapMock).not.toHaveBeenCalled()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('日期清单加载失败 → 原样带出错误信息', async () => {
    datesMock.mockRejectedValue(new Error('清单接口 503'))
    renderWithClient(<DataExport />)
    await expect(screen.findByText('清单接口 503')).resolves.toBeTruthy()
  })

  it('日期清单为空 → 诚实空态「暂无归档快照日期」，不伪造日期', async () => {
    datesMock.mockResolvedValue([])
    renderWithClient(<DataExport />)
    await expect(screen.findByText('暂无归档快照日期')).resolves.toBeTruthy()
  })

  it('选中归档日期 → 复用 SnapshotView 渲染 + 导出按钮可用', async () => {
    renderWithClient(<DataExport />)
    await pickDate('2026-03-01')
    expect(await screen.findByText('权威数据日')).toBeTruthy()
    expect(screen.getByText('已选 2026-03-01')).toBeTruthy()
    expect(snapMock).toHaveBeenCalledWith('2026-03-01')
    // jsdom 的 a.click() 会触发「Not implemented: navigation」噪声 → 桩掉原生 click，
    // 只验证导出入口不抛错（真实下载能力由浏览器决定，缺失时 downloadJson 已安全降级）。
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    expect(() => fireEvent.click(screen.getByText('导出 JSON'))).not.toThrow()
    clickSpy.mockRestore()
  })

  it('成功但无快照（data=null）→ 「该日期无归档快照」，不回退今日快照', async () => {
    snapMock.mockResolvedValue(null as unknown as DailySnapshot)
    renderWithClient(<DataExport />)
    await pickDate('2026-03-01')
    await expect(screen.findByText('该日期无归档快照')).resolves.toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('后端 not_found（该日确无归档）→ 仍走诚实空态，不误报为错误', async () => {
    // 真后端 /snapshot/<date> 对缺失归档返回 status=error / code=not_found 信封
    snapMock.mockRejectedValue(
      new ApiError('not_found', '数据文件缺失或为空：snapshots/2026-03-01.json'),
    )
    renderWithClient(<DataExport />)
    await pickDate('2026-03-01')
    await expect(screen.findByText('该日期无归档快照')).resolves.toBeTruthy()
    expect(screen.getByText('data/snapshots 中无该日期归档')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('网络/鉴权/解析失败（非 not_found）→ 如实报错 role=alert，绝不伪装成「无归档」', async () => {
    snapMock.mockRejectedValue(new ApiError('http_error', '快照接口 500'))
    renderWithClient(<DataExport />)
    await pickDate('2026-03-01')
    await expect(screen.findByText('快照接口 500')).resolves.toBeTruthy()
    expect(screen.queryByText('该日期无归档快照')).toBeNull()
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('未分类错误（普通 Error / ZodError）也按失败处理，不静默降级为空态', async () => {
    snapMock.mockRejectedValue(new Error('响应不符合统一信封'))
    renderWithClient(<DataExport />)
    await pickDate('2026-03-01')
    await expect(screen.findByText('响应不符合统一信封')).resolves.toBeTruthy()
    expect(screen.queryByText('该日期无归档快照')).toBeNull()
    expect(screen.getByRole('alert')).toBeTruthy()
  })
})
