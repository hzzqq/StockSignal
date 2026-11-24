import { useState } from 'react'
import {
  EXPORT_FORMATS,
  EXPORT_FORMAT_LABELS,
  STOCK_REPORT_FORMATS,
  type ExportBundleJson,
  type ExportFormat,
  type StockReport,
  type StockReportFormat,
} from '@/api/schemas/exportBundle'
import {
  downloadExportBundle,
  getExportBundleJson,
  getStockReport,
  saveBlob,
} from '@/api/exportBundle'
import { ApiError } from '@/api/client'
import { Card } from '@/shared/ui/Card'
import { Select } from '@/shared/ui/Field'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { fmtNum } from '@/lib/format'

/**
 * 95 数据导出 · 平台数据集导出 + 一键研报（parity D）。
 *
 * 诚实红线：available=false / skipped 全清单 / 研报「数据不可用」板块一律原样透出，
 * 不补零、不伪造导出成功；下载能力缺失时如实提示，不静默假装成功。
 */
const LABEL_CLS = 'block text-label text-sf-ink-3'
const INPUT_CLS =
  'mt-1 rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent'
const BTN_CLS =
  'rounded-tile border border-sf-line px-3 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-50'
const CODE_RE = /^\d{6}$/

function errText(e: unknown): string {
  if (e instanceof ApiError) {
    return e.code === 'unavailable' ? e.reason : `${e.message}`
  }
  return e instanceof Error ? e.message : String(e)
}

export function ExportBundlePanel() {
  const [fmt, setFmt] = useState<ExportFormat>('zip')
  const [period, setPeriod] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [jsonPreview, setJsonPreview] = useState<ExportBundleJson | null>(null)

  const periodValid = period.trim() === '' || /^\d{8}$/.test(period.trim())
  const codeValid = code.trim() === '' || CODE_RE.test(code.trim())
  const canSubmit = periodValid && codeValid && !busy

  async function submit() {
    setBusy(true)
    setNotice(null)
    setError(null)
    setJsonPreview(null)
    const params = {
      period: period.trim() || undefined,
      code: code.trim() || undefined,
    }
    try {
      if (fmt === 'json') {
        const data = await getExportBundleJson(params)
        setJsonPreview(data)
        if (!data.available) {
          setNotice('本次导出无可用数据集')
        }
      } else {
        const { blob, filename } = await downloadExportBundle(fmt, params)
        const okSaved = saveBlob(blob, filename)
        setNotice(okSaved
          ? `已下载 ${filename}（单数据集失败不影响整体，见包内 manifest）`
          : '浏览器不支持下载能力，文件已生成但未能保存')
      }
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="平台数据集导出（CSV / Excel / PDF / JSON）">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Select
            label="导出格式"
            aria-label="导出格式"
            value={fmt}
            onChange={(e) => setFmt(e.target.value as ExportFormat)}
          >
            {EXPORT_FORMATS.map((f) => (
              <option key={f} value={f}>
                {EXPORT_FORMAT_LABELS[f]}
              </option>
            ))}
          </Select>
          <label className={LABEL_CLS}>
            报告期（可选，YYYYMMDD）
            <input
              aria-label="导出报告期"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="如 20260630"
              className={INPUT_CLS}
            />
          </label>
          {/* 个股代码：统一 StockSearchInput；留空=全市场语义不变（code='' 时 params.code=undefined）。
              受控清空可行：value='' 经内部 useEffect 同步显示，下方清空按钮置空字符串即恢复全市场。 */}
          <div className="space-y-1">
            <StockSearchInput
              label="个股代码（可选，留空=全市场）"
              value={code}
              onSelect={(c) => setCode(c)}
            />
            {code.trim() !== '' && (
              <button
                type="button"
                onClick={() => setCode('')}
                className="text-label text-sf-ink-3 hover:text-sf-accent"
              >
                清空个股代码（恢复全市场导出）
              </button>
            )}
          </div>
        </div>
        {!periodValid && (
          <p className="text-label text-sf-danger">报告期须为 8 位数字（YYYYMMDD）</p>
        )}
        {!codeValid && (
          <p className="text-label text-sf-danger">个股代码须为 6 位数字</p>
        )}
        <button type="button" onClick={submit} disabled={!canSubmit} className={BTN_CLS}>
          {busy ? '导出中…' : '开始导出'}
        </button>
        {notice && <span className="ml-2 text-label text-sf-ink-2">{notice}</span>}
        {error && <p className="text-label text-sf-danger">导出失败：{error}</p>}
        {jsonPreview && (
          <JsonBundlePreview data={jsonPreview} />
        )}
        <p className="text-xs text-sf-ink-3">
          数据集：行业板块资金流向 / 北向资金 / 大盘主力净流入 30 日 / 个股主力资金 /
          业绩报表 / 组合持仓盈亏与汇总 / 自选股实时快照。单个数据集失败不影响整体，
          失败清单如实透出，不补零。
        </p>
      </div>
    </Card>
  )
}

function JsonBundlePreview({ data }: { data: ExportBundleJson }) {
  const names = Object.keys(data.datasets)
  if (!data.available && names.length === 0) {
    return (
      <div className="space-y-1 rounded-tile border border-sf-line p-3">
        <p className="text-label text-sf-danger">无可用数据集</p>
        {data.reason && <p className="text-label text-sf-ink-2">{data.reason}</p>}
        {data.skipped.length > 0 && (
          <p className="text-label text-sf-ink-3">失败清单：{data.skipped.join('、')}</p>
        )}
      </div>
    )
  }
  return (
    <div className="space-y-3">
      {data.skipped.length > 0 && (
        <p className="text-label text-sf-warn">以下数据集本次不可用（已跳过）：{data.skipped.join('、')}</p>
      )}
      {names.map((name) => {
        const rows = data.datasets[name]
        const cols = rows.length > 0 ? Object.keys(rows[0]) : []
        return (
          <div key={name} className="space-y-1">
            <p className="text-label text-sf-ink-2">{name}（{rows.length} 行）</p>
            {rows.length === 0 ? (
              <p className="text-xs text-sf-ink-3">空数据集，不伪造行。</p>
            ) : (
              <div className="max-h-48 overflow-auto rounded-tile border border-sf-line">
                <table className="w-full text-body">
                  <thead className="sticky top-0 bg-sf-surface">
                    <tr className="text-sf-ink-3 text-left text-label">
                      {cols.map((c) => (
                        <th key={c} className="py-1 px-2 font-normal">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="text-sf-ink-2">
                    {rows.slice(0, 20).map((r, i) => (
                      <tr key={i} className="border-t border-sf-line">
                        {cols.map((c) => (
                          <td key={c} className="py-1 px-2 tabular-nums">{fmtNum(r[c])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {rows.length > 20 && (
              <p className="text-xs text-sf-ink-3">仅预览前 20 行，完整数据请用 ZIP / Excel 导出。</p>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function StockReportPanel() {
  const [codeInput, setCodeInput] = useState('600519')
  // 选中项名称（来自搜索结果 item），仅用于回显；未匹配到名称（直接按代码查询）时如实只显代码。
  const [codeName, setCodeName] = useState<string | null>(null)
  const [format, setFormat] = useState<StockReportFormat>('html')
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState<StockReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!CODE_RE.test(codeInput.trim())) {
      setError('股票代码须为 6 位数字')
      return
    }
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      const rep = await getStockReport(codeInput.trim(), format)
      setReport(rep)
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  function download(rep: StockReport) {
    const content = rep.html ?? rep.md
    if (content == null) return
    const ext = rep.html != null ? 'html' : 'md'
    const mime = ext === 'html' ? 'text/html' : 'text/markdown'
    const okSaved = saveBlob(
      new Blob([content], { type: `${mime};charset=utf-8` }),
      `研报_${rep.code ?? codeInput}.${ext}`,
    )
    if (!okSaved) {
      setError('浏览器不支持下载能力，文件已生成但未能保存')
    }
  }

  return (
    <Card title="一键研报（个股 HTML / Markdown）">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          {/* 股票代码：统一 StockSearchInput + name(code) 回显；提交前 6 位校验保留。 */}
          <div className="space-y-1">
            <StockSearchInput
              label="股票代码"
              value={codeInput}
              onSelect={(c, item) => {
                setCodeInput(c)
                setCodeName(item?.name ?? null)
              }}
            />
            {codeName && CODE_RE.test(codeInput.trim()) && (
              <p className="text-label text-sf-ink-2">{`已选标的：${codeName}（${codeInput.trim()}）`}</p>
            )}
          </div>
          <Select
            label="格式"
            aria-label="研报格式"
            value={format}
            onChange={(e) => {
              // 切格式即失效旧研报：旧内容只对应旧格式，残留会让
              // 「下载 Markdown 文件」按钮实下 HTML 文件（格式不符真缺陷）。
              setFormat(e.target.value as StockReportFormat)
              setReport(null)
              setError(null)
            }}
          >
            {STOCK_REPORT_FORMATS.map((f) => (
              <option key={f} value={f}>{f === 'html' ? 'HTML 自包含' : 'Markdown'}</option>
            ))}
          </Select>
          <div className="flex items-end">
            <button type="button" onClick={submit} disabled={busy} className={BTN_CLS}>
              {busy ? '装配中…' : '生成研报'}
            </button>
          </div>
        </div>
        {error && <p className="text-label text-sf-danger">{error}</p>}
        {report && !report.available && (
          <div className="rounded-tile border border-sf-line p-3">
            <p className="text-label text-sf-danger">研报不可用</p>
            <p className="text-label text-sf-ink-2">{report.reason ?? '后端未返回原因'}</p>
          </div>
        )}
        {report?.available && (
          <div className="space-y-2">
            <p className="text-label text-sf-ink-2">
              {report.name ?? report.code} · 数据覆盖率 {report.coverage_pct == null ? '—' : `${report.coverage_pct}%`} ·
              {' '}缺数据板块如实标注「数据不可用」，绝不编造。
            </p>
            {report.skipped_blocks && report.skipped_blocks.length > 0 && (
              <p className="text-label text-sf-warn">
                不可用板块：{report.skipped_blocks.join('、')}
              </p>
            )}
            <button
              type="button"
              onClick={() => download(report)}
              className={BTN_CLS}
            >
              下载 {format === 'html' ? 'HTML' : 'Markdown'} 文件
            </button>
          </div>
        )}
      </div>
    </Card>
  )
}
