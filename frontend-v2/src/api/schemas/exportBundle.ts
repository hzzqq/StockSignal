import { z } from 'zod'

/**
 * 95 数据导出（parity D）：后端 GET /api/v2/read/export-bundle 与 /stock-report。
 *
 * 诚实红线：
 *  - 7 个数据集服务端 best-effort 装配，单个失败进 skipped 全清单，绝不补零；
 *  - 全部失败 / 格式化失败 → available=false + reason（后端不返回半个损坏文件）；
 *  - 研报缺数据的板块明确标注「数据不可用」，绝不编造；coverage_pct=0 时 available=false。
 */
export const EXPORT_FORMATS = ['zip', 'excel', 'pdf', 'json'] as const
export type ExportFormat = (typeof EXPORT_FORMATS)[number]

export const EXPORT_FORMAT_LABELS: Record<ExportFormat, string> = {
  zip: 'ZIP（全数据集 CSV 打包）',
  excel: 'Excel 多 Sheet',
  pdf: 'PDF 中文摘要',
  json: 'JSON（页面预览）',
}

/** json 档：datasets 为 {数据集名: 行记录[]}，行内值已 null 安全化。 */
export const ExportBundleJsonSchema = z.object({
  available: z.boolean(),
  datasets: z
    .record(z.string(), z.array(z.record(z.string(), z.unknown())))
    .default({}),
  skipped: z.array(z.string()).default([]),
  reason: z.string().nullable().default(null),
})

export type ExportBundleJson = z.infer<typeof ExportBundleJsonSchema>

/** 一键研报：装配/渲染失败时只有 {available, reason}，其余字段缺省宽容。 */
export const StockReportSchema = z.object({
  available: z.boolean(),
  code: z.string().optional(),
  name: z.string().nullable().optional(),
  coverage_pct: z.number().optional(),
  skipped_blocks: z.array(z.string()).optional(),
  reason: z.string().nullable().optional(),
  html: z.string().optional(),
  md: z.string().optional(),
})

export type StockReport = z.infer<typeof StockReportSchema>

export const STOCK_REPORT_FORMATS = ['html', 'md'] as const
export type StockReportFormat = (typeof STOCK_REPORT_FORMATS)[number]

/** 64 投研圆桌静态交付物：meta 只给 KPI + 双格式可用状态，content 才是原文。 */
export const RoundtableKpiSchema = z.object({
  label: z.string(),
  value: z.string(),
  meta: z.string(),
})

export const RoundtableReportMetaSchema = z.object({
  available: z.boolean(),
  as_of: z.string(),
  kpis: z.array(RoundtableKpiSchema).default([]),
  md_available: z.boolean(),
  html_available: z.boolean(),
  source_note: z.string(),
  reason: z.string().nullable().default(null),
})

export const RoundtableReportContentSchema = z.object({
  available: z.boolean(),
  format: z.enum(['md', 'html']),
  filename: z.string(),
  mime: z.string(),
  as_of: z.string(),
  content: z.string(),
  reason: z.string().nullable().default(null),
})

export type RoundtableReportMeta = z.infer<typeof RoundtableReportMetaSchema>
export type RoundtableReportContent = z.infer<typeof RoundtableReportContentSchema>
