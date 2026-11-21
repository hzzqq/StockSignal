import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ExportBundlePanel, StockReportPanel } from './ExportBundlePanels'
import { getExportBundleJson, downloadExportBundle, getStockReport, saveBlob } from '@/api/exportBundle'
import { stockReportFixture, exportBundleJsonFixture } from '@/mocks/fixturesBatchD'

// 面板内 StockSearchInput 使用 react-query（股票搜索），须挂 Provider 才能渲染。
function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

vi.mock('@/api/exportBundle', () => ({
  getExportBundleJson: vi.fn(),
  downloadExportBundle: vi.fn(),
  getStockReport: vi.fn(),
  saveBlob: vi.fn(),
}))
const reportMock = vi.mocked(getStockReport)
const jsonMock = vi.mocked(getExportBundleJson)
const dlMock = vi.mocked(downloadExportBundle)
const saveMock = vi.mocked(saveBlob)

beforeEach(() => {
  reportMock.mockReset().mockResolvedValue(stockReportFixture)
  jsonMock.mockReset().mockResolvedValue(exportBundleJsonFixture)
  dlMock.mockReset().mockResolvedValue({
    blob: new Blob(['x']),
    filename: 'StockSignal_数据导出.zip',
  })
  saveMock.mockReset().mockReturnValue(true)
})

describe('ExportBundlePanel · 平台数据集导出', () => {
  it('json 预览：available=true → 数据集表格 + skipped 清单如实透出', async () => {
    renderWithClient(<ExportBundlePanel />)
    fireEvent.change(screen.getByRole('combobox', { name: '导出格式' }), {
      target: { value: 'json' },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始导出' }))
    await screen.findByText(/行业板块资金流向.csv（2 行）/)
    expect(screen.getByText(/以下数据集本次不可用/)).toBeTruthy()
    expect(jsonMock).toHaveBeenCalledTimes(1)
  })

  it('文件档：saveBlob 成功 → 提示已下载文件名', async () => {
    renderWithClient(<ExportBundlePanel />)
    fireEvent.click(screen.getByRole('button', { name: '开始导出' }))
    await waitFor(() =>
      expect(screen.getByText(/已下载 StockSignal_数据导出.zip/)).toBeTruthy(),
    )
    expect(dlMock).toHaveBeenCalledWith('zip', { period: undefined, code: undefined })
    expect(saveMock).toHaveBeenCalledTimes(1)
  })

  it('文件档：saveBlob 失败 → 如实提示「未能保存」，不静默假装成功', async () => {
    saveMock.mockReturnValue(false)
    renderWithClient(<ExportBundlePanel />)
    fireEvent.click(screen.getByRole('button', { name: '开始导出' }))
    await waitFor(() =>
      expect(screen.getByText(/未能保存/)).toBeTruthy(),
    )
  })
})

describe('StockReportPanel · 一键研报', () => {
  it('生成研报 → 覆盖率 + 不可用板块 + 下载按钮', async () => {
    renderWithClient(<StockReportPanel />)
    fireEvent.click(screen.getByRole('button', { name: '生成研报' }))
    await screen.findByText(/数据覆盖率 75%/)
    expect(screen.getByText(/不可用板块/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '下载 HTML 文件' })).toBeTruthy()
  })

  it('切格式未重新生成 → 旧研报立即失效（否则「下载 Markdown」实下 HTML 文件）', async () => {
    renderWithClient(<StockReportPanel />)
    fireEvent.click(screen.getByRole('button', { name: '生成研报' }))
    await screen.findByText(/数据覆盖率 75%/)
    fireEvent.change(screen.getByRole('combobox', { name: '研报格式' }), {
      target: { value: 'md' },
    })
    expect(screen.queryByText(/数据覆盖率/)).toBeNull()
    expect(screen.queryByRole('button', { name: /下载/ })).toBeNull()
    expect(screen.queryByText(/不可用板块/)).toBeNull()
  })

  it('saveBlob 失败 → 如实提示「未能保存」，不静默假装成功', async () => {
    saveMock.mockReturnValue(false)
    renderWithClient(<StockReportPanel />)
    fireEvent.click(screen.getByRole('button', { name: '生成研报' }))
    await screen.findByText(/数据覆盖率 75%/)
    fireEvent.click(screen.getByRole('button', { name: '下载 HTML 文件' }))
    await waitFor(() => expect(screen.getByText(/未能保存/)).toBeTruthy())
  })

  it('研报不可用 → 显后端 reason，不出现下载按钮', async () => {
    reportMock.mockResolvedValue({
      available: false,
      reason: '本报告无有效数据板块（覆盖率 0%）',
    })
    renderWithClient(<StockReportPanel />)
    fireEvent.click(screen.getByRole('button', { name: '生成研报' }))
    await screen.findByText('研报不可用')
    expect(screen.queryByRole('button', { name: /下载/ })).toBeNull()
  })
})
