import { http } from 'msw'
import {
  earningsHunterFixture,
  earningsHunterUnavailableFixture,
  exportBundleJsonFixture,
  exportBundleJsonAllFailedFixture,
  stockReportFixture,
  stockReportUnavailableFixture,
  nlExecuteFixture,
  nlExecuteUnavailableFixture,
} from './fixturesBatchD'
import { writeOk, writeBadRequest } from './writeEnvelope'
import { EARNINGS_PERIODS, EARNINGS_SIGNAL_ORDER } from '@/api/schemas/earningsHunter'

/**
 * parity D 批次 MSW 演示 handler（77 财报猎手 / 81 NL 执行 / 95 导出）。
 *
 * 全部为只读 GET；演示态夹具不代表真实行情。参数非法按真后端语义
 * 返回 422 validation_error（writeBadRequest）。
 */

const PERIOD_SET = new Set<string>(EARNINGS_PERIODS)
const SIGNAL_SET = new Set<string>(EARNINGS_SIGNAL_ORDER)

/** 演示态过滤：按 min_pct / signals 对夹具行做与真后端同语义的筛选。 */
function demoScan(
  minPct: number | null,
  signals: string[],
): typeof earningsHunterFixture {
  let rows = [...earningsHunterFixture.rows]
  if (signals.length > 0) {
    rows = rows.filter((r) => signals.includes(signalOf(r['预告类型'])))
  }
  if (minPct != null) {
    rows = rows.filter(
      (r) => typeof r['净利润变动幅度'] === 'number' && (r['净利润变动幅度'] as number) >= minPct,
    )
  }
  const counts: Record<string, number> = {}
  for (const s of EARNINGS_SIGNAL_ORDER) counts[s] = 0
  for (const r of rows) {
    const sig = signalOf(r['预告类型'])
    counts[sig] = (counts[sig] != null ? counts[sig] : 0) + 1
  }
  return {
    ...earningsHunterFixture,
    rows,
    n_total: rows.length,
    signal_counts: counts,
  }
}

/** 与 modules.financial_hunter.signal_of 同语义的演示映射。 */
function signalOf(typeText: unknown): string {
  const t = String(typeText ?? '')
  if (t.includes('预增') || t.includes('扭亏')) return '利好'
  if (t.includes('略增') || t.includes('续盈')) return '偏多'
  if (t.includes('预减') || t.includes('首亏')) return '利空'
  if (t.includes('略减') || t.includes('续亏')) return '偏空'
  return '中性'
}

export const batchDHandlers = [
  // 77 财报猎手 · 业绩预告信号扫描
  http.get('/api/v2/read/earnings-hunter', ({ request }) => {
    const url = new URL(request.url)
    const period = url.searchParams.get('period') ?? ''
    if (!PERIOD_SET.has(period)) {
      return writeBadRequest(`period 须为 ${EARNINGS_PERIODS.join('/')} 之一`)
    }
    const minPctRaw = url.searchParams.get('min_pct')
    let minPct: number | null = null
    if (minPctRaw != null && minPctRaw !== '') {
      const v = Number(minPctRaw)
      if (!Number.isFinite(v) || v < -200 || v > 200) {
        return writeBadRequest('min_pct 须为 -200~200 的数字')
      }
      minPct = v
    }
    const signalsRaw = url.searchParams.get('signals') ?? ''
    const signals = signalsRaw === '' ? [] : signalsRaw.split(',')
    if (signals.some((s) => !SIGNAL_SET.has(s))) {
      return writeBadRequest(`signals 仅允许 ${EARNINGS_SIGNAL_ORDER.join('/')}`)
    }
    // 演示态：2025 中报夹具为「未到披露期」诚实降级样例
    if (period === '20250630') {
      return writeOk(earningsHunterUnavailableFixture)
    }
    return writeOk(demoScan(minPct, signals))
  }),

  // 95 数据导出 · json 档（zip/excel/pdf 为文件字节，MSW 演示态不模拟二进制下载；
  // 真下载走真实后端。演示页按 json 档预览 + 下载按钮提示需连真后端）。
  http.get('/api/v2/read/export-bundle', ({ request }) => {
    const url = new URL(request.url)
    const format = url.searchParams.get('format') ?? ''
    if (!['zip', 'excel', 'pdf', 'json'].includes(format)) {
      return writeBadRequest('format 须为 zip / excel / pdf / json 之一')
    }
    const code = url.searchParams.get('code') ?? ''
    if (code !== '' && !/^\d{6}$/.test(code)) {
      return writeBadRequest('code 须为 6 位数字股票代码')
    }
    const period = url.searchParams.get('period') ?? ''
    if (period !== '' && !/^\d{8}$/.test(period)) {
      return writeBadRequest('period 须为 8 位数字（YYYYMMDD）')
    }
    // 演示态：带 period=20250101 时返回「全失败」诚实降级样例
    if (period === '20250101') {
      return writeOk(exportBundleJsonAllFailedFixture)
    }
    if (format !== 'json') {
      // 非二进制档的演示态：诚实说明 MSW 不模拟文件字节
      return writeBadRequest('MSW 演示态仅支持 json 预览；zip / excel / pdf 请连接真实后端')
    }
    return writeOk(exportBundleJsonFixture)
  }),

  // 95 一键研报
  http.get('/api/v2/read/stock-report', ({ request }) => {
    const url = new URL(request.url)
    const code = url.searchParams.get('code') ?? ''
    if (!/^\d{6}$/.test(code)) {
      return writeBadRequest('code 须为 6 位数字股票代码')
    }
    const format = url.searchParams.get('format') ?? ''
    if (!['html', 'md'].includes(format)) {
      return writeBadRequest('format 须为 html 或 md')
    }
    // 演示态：000000 视为无效标的 → 覆盖率 0 诚实降级样例
    if (code === '000000') {
      return writeOk(stockReportUnavailableFixture)
    }
    const base = { ...stockReportFixture, code }
    if (format === 'md') {
      const { html: _html, ...rest } = base
      void _html
      return writeOk({ ...rest, md: '# 贵州茅台 · 个股研报（演示态）\n\n技术面 / 资金面 / 风险排雷装配样例。' })
    }
    return writeOk(base)
  }),

  // 81 自然语言选股 · 执行
  http.post('/api/v2/nl-screen/execute', async ({ request }) => {
    const raw: unknown = await request.json().catch(() => ({}))
    const body = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
    const query = typeof body.query === 'string' ? body.query.trim() : ''
    if (!query || query.length > 200) {
      return writeBadRequest('query 须为 1~200 字的选股意图描述')
    }
    const scope = body.scope ?? 'all'
    if (!['local_api', 'akspot', 'all'].includes(String(scope))) {
      return writeBadRequest('scope 须为 local_api / akspot / all 之一')
    }
    // 演示态：query 含「无法解析」→ 全未理解诚实降级样例
    if (query.includes('无法解析')) {
      return writeOk({
        ...nlExecuteUnavailableFixture,
        reason: '未能从语句解析出任何选股条件',
        query,
        spec: { ...nlExecuteFixture.spec, unparsed: ['无法解析'] },
      })
    }
    return writeOk({ ...nlExecuteFixture, query, scope: String(scope) })
  }),
]
