import { useState, type FormEvent } from 'react'
import { Link } from '@tanstack/react-router'
import type { AppPath } from '@/nav/nav'
import { useNlScreen } from '@/lib/queries'
import type { NlScreen, NlSpec } from '@/api/schemas/read'
import { V1_PAGES } from '@/features/catalog/v1Pages.generated'
import { mappingOf, type V2Status } from '@/features/catalog/v2Mapping'
import { v1PageUrl } from '@/lib/preferences'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'
import { NlExecutePanel } from './NlExecutePanel'

/**
 * 选股框架（/stock/screener）：把 v1「31 形态选股 / 33 ETF筛选 / 81 自然语言选股」
 * 三类选股意图**如实收进** v2 的统一入口。
 *
 * ⚠️ 诚实红线（ DESIGN.md / v2Mapping 四档口径）：
 *  - v2 只聚合**真实已落地**的选股能力，入口全部指向真实路由，不做假按钮；
 *  - 81 的「语义解析层」由 /api/v2/read/nl-screen 真搬进 v2（纯函数、不触网），
 *    只透明展示「听懂了什么」，**绝不返回或编造候选标的**；筛选执行仍仅 v1；
 *  - 31/33/81 的落地状态一律从 v2Mapping / v1Pages.generated 单一真理源读取，
 *    v1-pinned 项如实标注「v2 不做等价实现」并给 v1 直达链接，不伪装成已迁移。
 *  - 本页是入口聚合与状态说明，**列出 ≠ 已实现**。
 */

interface Entry {
  to: AppPath
  label: string
  desc: string
}

/** v2 已真实落地的选股相关能力（与 router.tsx 路由一一对应，非假入口）。 */
const ENTRIES: readonly Entry[] = [
  { to: '/recommend', label: '每日荐股', desc: '荐股引擎结果（31 形态选股的承接页，只读展示）' },
  { to: '/stock/six-dim', label: '六维评分', desc: '个股六维打分（34 体检扫描的 v2 等价页）' },
  { to: '/stock/research', label: '个股研究', desc: '单票深度研究与 K 线' },
  { to: '/stock/fundamentals', label: '基本面分析', desc: '财务三表与基本面指标' },
  { to: '/stock/compare', label: '个股对比', desc: '多票横向对照' },
  { to: '/factor', label: '因子分析', desc: '因子分层与暴露' },
  { to: '/xingchen', label: '星辰 AI 助手', desc: '自然语言对话式投研（非结构化选股筛选器，不等价）' },
]

/** 三页 v1 选股意图：状态与去向由 v2Mapping 单一真理源给出，前端不手写结论。 */
const LEGACY_FILES = ['31_形态选股.py', '33_ETF筛选.py', '81_自然语言选股.py'] as const

const STATUS_LABEL: Record<V2Status, string> = {
  native: '已由 v2 承接',
  data: '仅关联只读数据',
  'v1-only': '待迁移',
  'v1-pinned': 'v1 保留（v2 不做等价实现）',
}

function joinOrDash(list: string[] | undefined): string {
  return list && list.length > 0 ? list.join('、') : '—'
}

function fmtVal(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) return String(v)
  if (typeof v === 'string') return v
  return '—'
}

const OP_LABEL: Record<string, string> = {
  lt: '<', lte: '≤', gt: '>', gte: '≥', eq: '=', ne: '≠',
}

function SpecView({ data }: { data: NlScreen }) {
  const s: NlSpec | null | undefined = data.spec
  if (!s) return <div className="text-xs text-sf-ink-3">解析结果为空（后端诚实降级，不补默认条件）。</div>
  const filters = s.filters ?? []

  return (
    <div className="space-y-3">
      <div className="text-xs text-sf-ink-3">
        原始查询：<span className="text-sf-ink">{data.query ?? '—'}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat label="板块（归一化语义码）" value={joinOrDash(s.boards)} />
        <Stat label="排序字段" value={s.sort ?? '—'} />
        <Stat label="排序方向" value={s.sort_dir ?? '—'} />
        <Stat label="取前 N 只" value={s.limit == null ? '—' : String(s.limit)} />
        <Stat label="概念/行业词" value={joinOrDash(s.concepts)} />
        <Stat label="排除板块" value={joinOrDash(s.exclude_boards)} />
      </div>

      <div>
        <div className="text-label text-sf-ink-3 mb-1">筛选条件（{filters.length}）</div>
        {filters.length === 0 ? (
          <div className="text-xs text-sf-ink-3">未解析出数值条件（如实留空，不臆造）。</div>
        ) : (
          <ul className="text-xs text-sf-ink space-y-1">
            {filters.map((f, i) => (
              <li key={`${f.field}-${i}`}>
                <span className="text-sf-ink-3">{f.raw ?? `${f.field} ${OP_LABEL[f.op] ?? f.op}`}</span>
                {'　'}→ {f.field} {OP_LABEL[f.op] ?? f.op} {fmtVal(f.value)}
                {f.unit ? <span className="text-sf-ink-3">（{f.unit}）</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Stat label="排除概念/名字片段" value={joinOrDash(s.exclude_concepts)} />
        <Stat label="没听懂的词" value={joinOrDash(s.unparsed)} />
        <Stat label="解析异常说明" value={joinOrDash(s.errors)} />
      </div>

      <div className="rounded-tile bg-sf-surface-2 px-3 py-2 text-xs text-sf-ink-3">
        ⚠️ 以上只是「系统听懂了什么」的透明解析，<span className="text-sf-ink">不是筛选结果、也不含任何候选标的</span>。
        v2 不做联网行情筛选，v1 的 81/32 页才执行候选池筛选；未识别的词已如实列出，不猜测、不补齐。
      </div>

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}

export function Screener() {
  const [input, setInput] = useState('')
  const [submitted, setSubmitted] = useState('')
  const q = useNlScreen(submitted)

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitted(input.trim())
  }

  return (
    <div className="flow space-y-4">
      <SectionTitle as="h2">选股框架</SectionTitle>

      <div className="rounded-tile bg-sf-surface-2 px-3 py-2 text-xs text-sf-ink-3">
        ⚠️ <span className="font-medium text-sf-ink">列出 ≠ 已实现</span>：本页把 v1 三类选股意图
        （形态选股 / ETF 筛选 / 自然语言选股）收进统一入口，如实标注真实落地状态。
        v2 仅提供下列真实入口与自然语言「语义解析层」，不做联网筛选、不编造候选池。
      </div>

      <Card title="v2 已落地的选股能力（真实路由入口）">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {ENTRIES.map((e) => (
            <Link
              key={e.to}
              to={e.to}
              className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-2 hover:bg-sf-surface transition-colors"
            >
              <div className="text-body font-medium text-sf-ink">{e.label} →</div>
              <div className="text-label text-sf-ink-3 mt-0.5">{e.desc}</div>
            </Link>
          ))}
        </div>
      </Card>

      <Card title="自然语言选股 · 语义解析（81 页解析层 v2 化，只读不触网）">
        <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2 mb-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="例：创业板 市盈率<30 且 营收增长>20% 剔除ST 前10"
            aria-label="自然语言选股条件"
            className="flex-1 min-w-[16rem] rounded-tile border border-sf-line bg-sf-bg px-3 py-2 text-body text-sf-ink"
          />
          <button
            type="submit"
            className="rounded-tile bg-sf-accent text-sf-ink px-4 py-2 text-body"
          >
            解析
          </button>
        </form>
        <p className="text-label text-sf-ink-3 mb-2">
          输入一句大白话，系统把「听懂了什么」原样摊开。v2 只做语义解析，不会给出股票列表。
        </p>
        {submitted ? (
          <QueryState
            isLoading={q.isLoading}
            isError={q.isError}
            error={q.error}
            isEmpty={!!q.data && q.data.status !== 'ok'}
            emptyLabel="暂无法解析"
            emptyHint="后端诚实降级，不臆造解析结果"
          >
            {q.data && q.data.status === 'ok' ? <SpecView data={q.data} /> : null}
          </QueryState>
        ) : (
          <div className="text-xs text-sf-ink-3">尚未提交查询（不预填、不臆造解析结果）。</div>
        )}
      </Card>

      <NlExecutePanel />

      <Card title="v1 三类选股页 · 如实落地状态（单一真理源 v2Mapping）">
        <ul className="space-y-2">
          {LEGACY_FILES.map((file) => {
            const page = V1_PAGES.find((p) => p.file === file)
            if (!page) return null
            const m = mappingOf(page)
            return (
              <li key={file} className="border-b border-sf-line last:border-0 pb-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-body text-sf-ink">{page.name}</span>
                  <span className="text-label text-sf-ink-3">{STATUS_LABEL[m.status]}</span>
                </div>
                <div className="text-label text-sf-ink-3 mt-0.5">
                  {m.status === 'native'
                    ? (m.note ?? 'v2 已有等价页面')
                    : m.status === 'data'
                      ? `仅可查看关联只读数据：${m.dataLabel ?? '—'}（非等价功能）`
                      : (m.note ?? 'v2 不做等价实现')}
                </div>
                <div className="mt-1">
                  {m.status === 'native' && m.to ? (
                    <Link to={m.to} className="text-label text-sf-accent hover:underline">打开 v2 →</Link>
                  ) : (
                    <a
                      href={v1PageUrl(page.v1Url)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-label text-sf-accent hover:underline"
                    >
                      在 v1 打开 ↗
                    </a>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
        <div className="text-label text-sf-ink-3 mt-3">
          v1-pinned 项为架构决策：v2 明确不做等价实现，此处只给 v1 直达链接，不提供假入口。
        </div>
      </Card>

      <div className="text-xs text-sf-ink-3">
        {`口径与来源：入口清单对齐 router.tsx 真实路由；状态与说明读 v2Mapping.ts（单一真理源）； 语义解析复用 modules.nl_screen.parse_query（纯函数、确定性、不触网）。 全部内容为学习用途，`}
        <LeadText>不构成投资建议</LeadText>
        {`。`}
      </div>
    </div>
  )
}
