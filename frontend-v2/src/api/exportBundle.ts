import { apiFetch, apiFetchBlob } from './client'
import {
  ExportBundleJsonSchema,
  StockReportSchema,
  RoundtableReportMetaSchema,
  RoundtableReportContentSchema,
  type ExportBundleJson,
  type ExportFormat,
  type StockReport,
  type StockReportFormat,
  type RoundtableReportMeta,
  type RoundtableReportContent,
} from './schemas/exportBundle'

/**
 * 95 数据导出读端点（parity D）。json 档与研报走统一信封 apiFetch；
 * zip / excel / pdf 是文件字节直传，走 apiFetchBlob（JSON 错误信封会被识别并抛 ApiError）。
 */

export async function getExportBundleJson(params: {
  period?: string
  code?: string
}): Promise<ExportBundleJson> {
  const sp = new URLSearchParams({ format: 'json' })
  if (params.period) sp.set('period', params.period)
  if (params.code) sp.set('code', params.code)
  const data = await apiFetch<unknown>(`/v2/read/export-bundle?${sp.toString()}`)
  return ExportBundleJsonSchema.parse(data)
}

export interface ExportFileDownload {
  blob: Blob
  /** 后端 Content-Disposition 文件名；缺失时已回退本地生成名，恒非空。 */
  filename: string
}

/** 下载文件档（zip / excel / pdf）：返回 Blob 与后端 Content-Disposition 文件名。 */
export async function downloadExportBundle(
  fmt: Exclude<ExportFormat, 'json'>,
  params: { period?: string; code?: string } = {},
): Promise<ExportFileDownload> {
  const sp = new URLSearchParams({ format: fmt })
  if (params.period) sp.set('period', params.period)
  if (params.code) sp.set('code', params.code)
  const { blob, filename } = await apiFetchBlob(`/v2/read/export-bundle?${sp.toString()}`)
  return { blob, filename: filename ?? fallbackExportFilename(fmt) }
}

/** 后端未提供文件名时的本地回退（时间戳 + 中文语义名，与后端命名同风格）。 */
function fallbackExportFilename(fmt: Exclude<ExportFormat, 'json'>): string {
  const ext = fmt === 'zip' ? 'zip' : fmt === 'excel' ? 'xlsx' : 'pdf'
  const cn = fmt === 'zip' ? '数据导出' : fmt === 'excel' ? '数据汇总' : '数据摘要'
  return `StockSignal_${cn}.${ext}`
}

export async function getStockReport(
  code: string,
  format: StockReportFormat,
): Promise<StockReport> {
  const data = await apiFetch<unknown>(
    `/v2/read/stock-report?code=${encodeURIComponent(code)}&format=${format}`,
  )
  return StockReportSchema.parse(data)
}

/** 64 投研圆桌：meta（KPI + 双格式状态）与原文（供 MD 预览 / HTML 沙箱预览 / Blob 下载）。 */
export async function getRoundtableReportMeta(): Promise<RoundtableReportMeta> {
  const data = await apiFetch<unknown>('/v2/read/roundtable-report?format=meta')
  return RoundtableReportMetaSchema.parse(data)
}

export async function getRoundtableReportContent(
  format: 'md' | 'html',
): Promise<RoundtableReportContent> {
  const data = await apiFetch<unknown>(`/v2/read/roundtable-report?format=${format}`)
  return RoundtableReportContentSchema.parse(data)
}

/** 下载静态报告：原文来自统一信封，缺文件时后端 available=false，不造空 Blob。 */
export async function downloadRoundtableReport(format: 'md' | 'html'): Promise<boolean> {
  const report = await getRoundtableReportContent(format)
  if (!report.available || !report.content) return false
  return saveBlob(
    new Blob([report.content], { type: report.mime }),
    report.filename,
  )
}

/** 浏览器保存 Blob（环境不支持时静默降级并返回 false，UI 提示）。 */
export function saveBlob(blob: Blob, filename: string): boolean {
  try {
    if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return false
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return true
  } catch {
    return false
  }
}
