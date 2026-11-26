import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EChartsOption } from 'echarts'
import type { PredictionLogRow } from '@/api/schemas/read'
import { usePredictionLog } from '@/lib/queries'
import {
  downloadRoundtableReport,
  getRoundtableReportContent,
  getRoundtableReportMeta,
} from '@/api/exportBundle'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { ErrorState, Loading, QueryState } from '@/shared/ui/States'
import { EmptyStateModern } from '@/shared/ui/EmptyStateModern'
import { Markdown } from '@/features/xingchen/Markdown'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { fmtNum } from '@/lib/format'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'

/**
 * W3 后续簇 · 预测校准日志页（/predictions）。
 * 数据源：getPredictionLog → /api/v2/read/prediction-log → data/prediction_log.json。
 *
 * 诚实红线：hit / realized 为 null 表示「尚未兑现」，既不是「未命中」也不是 0。
 * 命中率分母只统计 hit 为 boolean 的已兑现样本；无可统计样本时显示「—」，不补 0%。
 * 本页是决策闭环的历史自评记录，不是未来预测。
 */
export function PredictionLogView() {
  const log = usePredictionLog()
  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <SectionTitle as="h2">预测校准日志</SectionTitle>
        <span className="text-label text-sf-ink-3">数据源 prediction_log</span>
        <a
          href="/breadth"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          ← 返回广度总览
        </a>
      </div>

      <RoundtableReport />

      <QueryState
        isLoading={log.isLoading}
        isError={log.isError}
        error={log.error}
        isEmpty={!log.data?.length}
        emptyLabel="暂无预测记录"
        emptyHint="数据文件缺失或日志为空，未做任何填充"
      >
        {log.data ? <PredictionBody rows={log.data} /> : null}
      </QueryState>
    </div>
  )
}

/**
 * 64 投研圆桌静态交付物（MD / HTML 双预览 + 双下载）。
 * 与 /predictions 的 prediction_log 是**两种数据源**：这里只读 deliverables/ 下固定文件，
 * 缺文件时显示诚实空态，绝不拿校准日志冒充静态报告。
 */
function RoundtableReport() {
  const meta = useQuery({
    queryKey: ['roundtable-report', 'meta'],
    queryFn: getRoundtableReportMeta,
    staleTime: Infinity,
  })
  const [view, setView] = useState<'md' | 'html'>('md')
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const formatAvailable = view === 'md'
    ? meta.data?.md_available === true
    : meta.data?.html_available === true
  const content = useQuery({
    queryKey: ['roundtable-report', view],
    queryFn: () => getRoundtableReportContent(view),
    enabled: formatAvailable,
    staleTime: Infinity,
  })

  async function onDownload(fmt: 'md' | 'html') {
    setDownloadError(null)
    try {
      const saved = await downloadRoundtableReport(fmt)
      if (!saved) setDownloadError('交付物缺失或浏览器不支持下载，未生成空文件')
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : '下载失败')
    }
  }

  const headerRight = (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => void onDownload('md')}
        disabled={meta.data?.md_available !== true}
        className="text-label px-2.5 py-1 rounded-tile border border-sf-line text-sf-ink-2 hover:text-sf-accent disabled:opacity-40"
      >
        ⬇️ 报告 MD
      </button>
      <button
        type="button"
        onClick={() => void onDownload('html')}
        disabled={meta.data?.html_available !== true}
        className="text-label px-2.5 py-1 rounded-tile border border-sf-line text-sf-ink-2 hover:text-sf-accent disabled:opacity-40"
      >
        ⬇️ 仪表盘 HTML
      </button>
    </div>
  )

  return (
    <Card title="投研圆桌 · 静态报告（2026-09-11）" right={headerRight}>
      {meta.isLoading ? <Loading label="加载圆桌报告…" /> : null}
      {meta.isError ? <ErrorState message={meta.error instanceof Error ? meta.error.message : '圆桌报告加载失败'} /> : null}
      {meta.data && !meta.data.available ? (
        <EmptyStateModern
          title="静态报告交付物缺失"
          description={meta.data.reason ?? 'MD / HTML 均不可用，未做任何填充'}
        />
      ) : null}
      {meta.data?.available ? (
        <div className="flow">
          <p className="text-label text-sf-ink-3">{meta.data.source_note}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {meta.data.kpis.map((k) => (
              <div key={k.label} className="rounded-tile border border-sf-line px-3 py-2">
                <div className="text-label text-sf-ink-3">{k.label}</div>
                <div className="text-title text-sf-ink-1 font-medium">{k.value}</div>
                <div className="text-label text-sf-ink-3">{k.meta}</div>
              </div>
            ))}
          </div>
          <div className="flex gap-2" role="tablist" aria-label="报告视图">
            <button
              type="button"
              role="tab"
              aria-selected={view === 'md'}
              onClick={() => setView('md')}
              className={`text-label px-3 py-1 rounded-tile ${view === 'md' ? 'bg-sf-accent text-white' : 'border border-sf-line text-sf-ink-2'}`}
            >
              报告正文 (MD)
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'html'}
              onClick={() => setView('html')}
              className={`text-label px-3 py-1 rounded-tile ${view === 'html' ? 'bg-sf-accent text-white' : 'border border-sf-line text-sf-ink-2'}`}
            >
              仪表盘预览 (HTML)
            </button>
          </div>
          {!formatAvailable ? (
            <EmptyStateModern title="该格式交付物缺失" description="未返回样例内容" />
          ) : content.isLoading ? (
            <Loading label="加载报告原文…" />
          ) : content.isError ? (
            <ErrorState message={content.error instanceof Error ? content.error.message : '原文加载失败'} />
          ) : content.data?.content ? (
            view === 'md' ? (
              <div className="text-body text-sf-ink-2"><Markdown content={content.data.content} /></div>
            ) : (
              <iframe
                title="投研圆桌仪表盘预览"
                sandbox=""
                srcDoc={content.data.content}
                className="w-full h-[560px] rounded-tile border border-sf-line bg-white"
              />
            )
          ) : null}
          {downloadError ? <ErrorState message={downloadError} /> : null}
        </div>
      ) : null}
    </Card>
  )
}

function PredictionBody({ rows }: { rows: PredictionLogRow[] }) {
  // 只把 hit 为布尔值的样本计入分母；未兑现（null/undefined）不参与统计。
  const settled = rows.filter((r) => typeof r.hit === 'boolean')
  const hits = settled.filter((r) => r.hit === true).length
  const rate = settled.length > 0 ? (hits / settled.length) * 100 : null
  const latest = rows[rows.length - 1]

  const trendOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['市场温度', '建议仓位%'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 40, right: 44, top: 28, bottom: 48 },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.date),
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: [
      {
        type: 'value',
        name: '温度',
        nameTextStyle: { color: CHART.ink3 },
        axisLabel: { color: CHART.ink2 },
        splitLine: { lineStyle: { color: CHART.line } },
      },
      {
        type: 'value',
        name: '仓位%',
        nameTextStyle: { color: CHART.ink3 },
        axisLabel: { color: CHART.ink2 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '市场温度',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: rows.map((r) => (typeof r.temp === 'number' ? r.temp : null)),
        itemStyle: { color: CHART.accent },
        lineStyle: { color: CHART.accent, width: 1.5 },
      },
      {
        name: '建议仓位%',
        type: 'bar',
        yAxisIndex: 1,
        data: rows.map((r) => (typeof r.pct === 'number' ? r.pct : null)),
        itemStyle: { color: CHART.ink3 },
      },
    ],
  }

  const recent = [...rows].slice(-12).reverse()

  return (
    <div className="flow">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="日志条数" value={fmtNum(rows.length)} sub="交易日" />
        <Stat label="已兑现" value={fmtNum(settled.length)} />
        <Stat label="命中" value={fmtNum(hits)} />
        <Stat
          label="命中率"
          value={rate === null ? '—' : `${rate.toFixed(1)}%`}
          sub={rate === null ? '无可统计样本' : `分母 ${settled.length} 条`}
        />
      </div>

      <Card title="口径说明">
        <p className="text-body text-sf-ink-2">
          命中率仅统计 hit 字段为布尔值的已兑现样本；尚未兑现的预测 hit / realized 为空，
          既不计入分子也不计入分母，不按「未命中」处理、不补零。
        </p>
        <p className="text-label text-sf-ink-3 mt-2">
          最新一条：{latest?.date ?? '—'} · 温度 {fmtNum(latest?.temp)} · 倾向 {latest?.bias ?? '—'}。
          本页是决策闭环的历史自评记录，不构成未来预测。
        </p>
      </Card>

      <Card title="v1 投研圆桌静态报告（未迁移）">
        <p className="text-body text-sf-ink-2">
          本页数据源是 <code>prediction_log</code> 校准日志与温度时序，与 v1《投研圆桌》的静态交付物
          <strong>不是同一数据源、也不是同一功能</strong>：v1 读取
          <code> deliverables/stock-partner/2026-09-11/ </code> 下的 Markdown 报告正文与内嵌 HTML 仪表盘片段，
          提供 MD / HTML 双下载与 KPI 带。v2 目前没有承接该静态报告的读取端点，
          因此报告展示与双下载<strong>尚未迁移</strong>，此处不以校准日志冒充等价功能。
        </p>
        <p className="text-label text-sf-ink-3 mt-2">
          {`如需查看 2026-09-11 收盘的投研圆桌原文，请从 v1 页面打开；`}
          <LeadText>本页仅作决策闭环的历史自评记录</LeadText>
          {`。`}
        </p>
      </Card>

      <Card title="温度与建议仓位时序">
        <EChart option={trendOption} height={260} ariaLabel="预测校准日志的市场温度与建议仓位逐日时序图" />
      </Card>

      <Card title="最近 12 条校准记录">
        <div className="overflow-x-auto">
          <table className="w-full text-body border-collapse">
            <caption className="sr-only">
              预测校准日志最近记录，含日期、市场温度、周期、倾向、建议仓位、事件调整、实际涨跌与兑现结果
            </caption>
            <thead>
              <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                <th scope="col" className="text-left py-2 pr-3 font-normal">日期</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">温度</th>
                <th scope="col" className="text-left py-2 pr-3 font-normal">周期</th>
                <th scope="col" className="text-left py-2 pr-3 font-normal">倾向</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">仓位%</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">实际涨跌</th>
                <th scope="col" className="text-left py-2 font-normal">兑现</th>
              </tr>
            </thead>
            <tbody className="text-sf-ink-2">
              {recent.map((r) => (
                <tr key={r.date} className="border-b border-sf-line last:border-0">
                  <td className="py-1.5 pr-3 tabular-nums">{r.date}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.temp)}</td>
                  <td className="py-1.5 pr-3">{r.cycle ?? '—'}</td>
                  <td className="py-1.5 pr-3">{r.bias ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.pct)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.realized)}</td>
                  <td className="py-1.5">
                    {typeof r.hit !== 'boolean' ? (
                      <span className="text-sf-ink-3">未兑现</span>
                    ) : r.hit ? (
                      <span className="text-sf-ok">命中</span>
                    ) : (
                      <span className="text-sf-warn">未命中</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-label text-sf-ink-3 mt-2">
          显示最近 {recent.length} 条（共 {rows.length} 条）；「未兑现」表示次日结果尚未落盘，不是判断错误。
        </p>
      </Card>
    </div>
  )
}
