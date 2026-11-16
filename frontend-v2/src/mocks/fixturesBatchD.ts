import type { z } from 'zod'
import type { EarningsHunter } from '@/api/schemas/earningsHunter'
import { EarningsHunterSchema } from '@/api/schemas/earningsHunter'
import type { ExportBundleJson, StockReport } from '@/api/schemas/exportBundle'
import { ExportBundleJsonSchema, StockReportSchema } from '@/api/schemas/exportBundle'
import type { NlExecuteResult } from '@/api/schemas/nlExecute'
import { NlExecuteResultSchema } from '@/api/schemas/nlExecute'

/**
 * parity D 批演示夹具（77 财报猎手 / 81 执行 / 95 导出）。
 *
 * 诚实红线：夹具是**演示态**样例（列名结构与东财业绩预告一致），仅用于 MSW 离线演示与
 * 契约漂移 A 段（fixture ↔ Zod 恒跑）；不代表真实行情 / 真实预告数据。B 段在真后端
 * 可用时拉真后端校验，见 contract-drift.test.ts。
 */

/** 东财业绩预告原始响应的典型中文列（v1 77 页 col_of 同源）。 */
const EARNINGS_ROWS: Record<string, unknown>[] = [
  {
    股票代码: '600519',
    股票简称: '贵州茅台',
    预告类型: '预增',
    公告日期: '2026-07-03',
    预告净利润: 41200000000,
    净利润变动幅度: 18.5,
    变动原因: '产品结构优化与渠道改革推进',
  },
  {
    股票代码: '000858',
    股票简称: '五粮液',
    预告类型: '略增',
    公告日期: '2026-07-05',
    预告净利润: 24800000000,
    净利润变动幅度: 9.2,
    变动原因: '核心产品放量',
  },
  {
    股票代码: '002594',
    股票简称: '比亚迪',
    预告类型: '扭亏',
    公告日期: '2026-07-08',
    预告净利润: 9050000000,
    净利润变动幅度: 32.4,
    变动原因: '出海车型毛利改善',
  },
]

export const earningsHunterFixture: EarningsHunter = {
  available: true,
  rows: EARNINGS_ROWS,
  n_total: 3,
  n_scanned: 5,
  signal_counts: { 利好: 2, 偏多: 1, 中性: 1, 偏空: 1, 利空: 0 },
  reason: null,
}

export const earningsHunterUnavailableFixture: EarningsHunter = {
  available: false,
  rows: [],
  n_total: null,
  n_scanned: null,
  signal_counts: {},
  reason: '该报告期暂无业绩预告数据（可能未到披露期或接口暂不可用）',
}


// ─────── 95 数据导出（json 档 + 一键研报）───────

export const exportBundleJsonFixture: ExportBundleJson = {
  available: true,
  datasets: {
    '行业板块资金流向.csv': [
      { 行业: '电子元件', 涨跌幅: 1.24, 主力净流入: 852000000 },
      { 行业: '半导体', 涨跌幅: 2.05, 主力净流入: 1200000000 },
    ],
    '自选股实时快照.csv': [
      { 代码: '600519', 名称: '贵州茅台', 现价: 1523.0, 涨跌幅: -0.62 },
    ],
  },
  skipped: ['北向资金.csv', '个股主力资金_600519.csv'],
  reason: null,
}

export const exportBundleJsonAllFailedFixture: ExportBundleJson = {
  available: false,
  datasets: {},
  skipped: ['行业板块资金流向.csv', '北向资金.csv'],
  reason: '全部数据集获取失败（接口异常或网络不可用），请稍后重试',
}

export const stockReportFixture: StockReport = {
  available: true,
  code: '600519',
  name: '贵州茅台',
  coverage_pct: 75,
  skipped_blocks: ['公告板块本次不可用，已标注「数据不可用」'],
  reason: null,
  html: '<html><body><h1>贵州茅台 · 个股研报（演示态）</h1><p>技术面 / 资金面 / 风险排雷装配样例。</p></body></html>',
}

export const stockReportUnavailableFixture: StockReport = {
  available: false,
  reason: '本报告无有效数据板块（覆盖率 0%）——可能行情源不可用或代码有误，请勿据此做任何判断',
}

// ─────── 81 自然语言选股执行 ───────

export const nlExecuteFixture: NlExecuteResult = {
  available: true,
  reason: null,
  query: '创业板 市盈率<30 前10',
  scope: 'all',
  spec: {
    boards: ['创业板'],
    filters: [{ field: '市盈率', op: '<', value: 30 }],
    sort: null,
    sort_dir: null,
    concepts: [],
    exclude_boards: [],
    exclude_concepts: [],
    unparsed: [],
    errors: [],
  },
  source_used: 'local_api',
  source_notes: ['local_api 命中 5 条候选'],
  n_universe: 5,
  n_matched: 3,
  n_rows: 3,
  rows: [
    { code: '300750', name: '宁德时代', 市盈率: 24.5, 收盘价: 218.4 },
    { code: '300059', name: '东方财富', 市盈率: 28.1, 收盘价: 19.7 },
    { code: '300015', name: '爱尔眼科', 市盈率: 29.9, 收盘价: 12.3 },
  ],
  gated_out: { count: 1, items: [{ code: '300001', name: '特发信息', reasons: ['近期异动'] }], note: null },
  elapsed_ms: 1234,
  note: '解析什么原样摊开；结果为真实筛选链路输出，非推荐',
}

export const nlExecuteUnavailableFixture: NlExecuteResult = {
  available: false,
  reason: '候选池获取失败（三级降级均未取得数据，执行需联网）：local_api 无数据；akspot 接口异常',
  query: '创业板 市盈率<30 前10',
  scope: 'all',
  spec: {
    boards: ['创业板'],
    filters: [{ field: '市盈率', op: '<', value: 30 }],
    sort: null,
    sort_dir: null,
    concepts: [],
    exclude_boards: [],
    exclude_concepts: [],
    unparsed: [],
    errors: [],
  },
  n_universe: 0,
  n_matched: 0,
  rows: [],
  gated_out: { count: 0, items: [], note: null },
  elapsed_ms: 89,
}

/** 契约漂移 A 段：D 批夹具 ↔ Zod 恒跑。 */
export const batchDFixturePairs: Array<{
  name: string
  schema: z.ZodTypeAny
  samples: unknown[]
}> = [
  {
    name: 'batch-d/earnings-hunter',
    schema: EarningsHunterSchema,
    samples: [earningsHunterFixture, earningsHunterUnavailableFixture],
  },
  {
    name: 'batch-d/export-bundle-json',
    schema: ExportBundleJsonSchema,
    samples: [exportBundleJsonFixture, exportBundleJsonAllFailedFixture],
  },
  {
    name: 'batch-d/stock-report',
    schema: StockReportSchema,
    samples: [stockReportFixture, stockReportUnavailableFixture],
  },
  {
    name: 'batch-d/nl-execute',
    schema: NlExecuteResultSchema,
    samples: [nlExecuteFixture, nlExecuteUnavailableFixture],
  },
]
