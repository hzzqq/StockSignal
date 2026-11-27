import { useMemo, useState } from 'react'
import type { EChartsOption } from 'echarts'
import type {
  PolicyDocument,
  PolicyTransmission,
  PolicyTransmissionEntry,
  SectorMap,
} from '@/api/schemas/read'
import type { FreshnessLevel } from '@/lib/freshness'
import { usePolicyDocuments, usePolicyTransmission, useSectorMap } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { FreshnessBadge } from '@/shared/ui/FreshnessBadge'
import { CollapsibleRankTable, type RankColumn } from '@/shared/ui/CollapsibleRankTable'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 政策事件传导工作台（只读）。
 *
 * 数据：policy-documents（政策原文清单）/ policy-transmission（单条本地传导链）/
 * sector-map（行业映射覆盖）。后端纯本地计算，不触网、不编造。
 *
 * 诚实红线：
 *  - publish_date 原样透出（缺失显「—」，绝不 now()/crawled_at 兜底）；
 *  - 缺失字段显「—」，不补 0；
 *  - derived（行业命中 / body_excerpt / 代码占位名）显式标注，非原文；
 *  - 关联度 = 文本共现，非收益预测；basis/disclaimer/derived_note/members_unavailable 原样透出；
 *  - 方向色用后端 dir_color（CHART 十六进制），不借用 A 股涨跌色 Tailwind class。
 */
function txt(v: unknown): string {
  return typeof v === 'string' && v.trim() !== '' ? v : '—'
}

function num(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? String(v) : '—'
}

function freshnessOf(isFresh: boolean | null | undefined): FreshnessLevel {
  if (isFresh === true) return 'ok'
  if (isFresh === false) return 'stale'
  return 'unknown'
}

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/
function directionColor(v: unknown): string {
  return typeof v === 'string' && HEX_COLOR.test(v) ? v : CHART.ink2
}

function rawList(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}

export function PolicyTransmission() {
  const [policyId, setPolicyId] = useState<string | null>(null)
  const docsQ = usePolicyDocuments(30)
  const transQ = usePolicyTransmission(policyId)
  const mapQ = useSectorMap()

  const docs = docsQ.data
  const items = docs?.items ?? []
  const docStats: Record<string, unknown> = docs?.stats ?? {}
  const docUnavailable = rawList(docs?.unavailable)
  const docsEmpty = !!docs && (items.length === 0 || docUnavailable.includes('policy_db_empty'))

  const trans = transQ.data
  const transUnavailable = rawList(trans?.unavailable)
  const transEmpty = !!trans && (trans.status === 'unavailable' || transUnavailable.length > 0)

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">政策事件传导</h2>
      <p className="text-body text-sf-ink-3">
        从政策原文出发，用本地行业映射做「标题 × 行业 → 标的」的共现传导链。<strong className="font-bold" style={{ color: 'var(--color-brand-1)' }}>关联度仅代表文本共现，
        不是受益程度，更不是收益预测</strong>；口径与免责声明原样展示在下方法说明卡。
      </p>

      <QueryState
        isLoading={docsQ.isLoading}
        isError={docsQ.isError}
        error={docsQ.error}
        isEmpty={docsEmpty}
        emptyLabel="政策库暂无原文"
        emptyHint="后端已诚实降级（policy_db_empty），未编造政策标题或日期"
        onRetry={() => docsQ.refetch()}
        retrying={docsQ.isRefetching}
      >
        {docs ? (
          <Card title="政策原文清单">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <Stat label="政策总数" value={num(docStats.total)} />
              <Stat label="最新原文日期" value={txt(docStats.latest_publish_date)} sub="数据原文日期，非抓取时间" />
              <Stat label="来源分布" value={docStats.by_source && typeof docStats.by_source === 'object' ? String(Object.keys(docStats.by_source).length) : '—'} />
              <Stat label="本页列出" value={num(items.length)} sub="limit=30" />
            </div>

            <div className="space-y-3">
              {items.map((d: PolicyDocument, i) => (
                <div
                  key={d.policy_id ?? `policy-${i}`}
                  className="rounded-tile border border-sf-line bg-sf-surface-2 px-3.5 py-3"
                >
                  <div className="text-body font-medium text-sf-ink">{txt(d.title)}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-label text-sf-ink-3">
                    <span>发布日期：{txt(d.publish_date)}</span>
                    <span>发文机关：{txt(d.issuing_body)}</span>
                    <span>文号：{txt(d.doc_number)}</span>
                    <FreshnessBadge level={freshnessOf(d.is_fresh)} />
                    <button
                      type="button"
                      onClick={() => setPolicyId(d.policy_id ?? null)}
                      disabled={!d.policy_id}
                      className="rounded-tile border border-sf-line px-2.5 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent disabled:opacity-50"
                      aria-label={`查看「${txt(d.title)}」的传导链`}
                    >
                      查看传导
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {docUnavailable.length > 0 && (
              <p className="mt-3 text-label text-sf-ink-3">本次不可用：{docUnavailable.join('、')}</p>
            )}
            {docs.note && <p className="mt-2 text-label text-sf-ink-3">{docs.note}</p>}
          </Card>
        ) : null}
      </QueryState>

      {policyId ? (
        <QueryState
          isLoading={transQ.isLoading}
          isError={transQ.isError}
          error={transQ.error}
          isEmpty={transEmpty}
          emptyLabel={trans && trans.reason ? trans.reason : '该政策的传导链暂不可用'}
          emptyHint="后端未取到本地行业映射或政策不存在，已诚实降级，未编造行业或标的"
        >
          {trans ? <TransmissionBody data={trans} /> : null}
        </QueryState>
      ) : (
        <Card title="传导链">
          <p className="text-body text-sf-ink-3">点击上方政策条目的「查看传导」，查看该政策的本地传导链与关联度。</p>
        </Card>
      )}

      <SectorCoverage data={mapQ.data} />
    </div>
  )
}

function TransmissionBody({ data }: { data: PolicyTransmission }) {
  const p = data.policy
  const entries = data.entries ?? []
  const sectors = data.sectors ?? []
  const conceptsHit = rawList(data.concepts_hit)
  const membersUnavailable = rawList(data.members_unavailable)

  const columns: RankColumn<PolicyTransmissionEntry>[] = useMemo(
    () => [
      {
        key: 'name',
        title: '标的',
        value: (r) => r.name ?? null,
        render: (r) => (
          <span>
            <span className="text-sf-ink">{txt(r.name)}</span>
            {r.name === r.code && r.code != null && (
              <span className="ml-1 text-label text-sf-warn" title="name 为代码占位，非原文证券简称（derived）">
                代码占位
              </span>
            )}
            <span className="ml-1 text-label text-sf-ink-3">{txt(r.code)}</span>
          </span>
        ),
      },
      {
        key: 'score',
        title: '关联度',
        align: 'right',
        sortable: true,
        value: (r) => (typeof r.score === 'number' && Number.isFinite(r.score) ? r.score : null),
        render: (r) => num(r.score),
      },
      {
        key: 'direction',
        title: '方向',
        value: (r) => r.direction ?? null,
        render: (r) => <span style={{ color: directionColor(r.dir_color) }}>{txt(r.direction)}</span>,
      },
      {
        key: 'concepts',
        title: '命中行业',
        value: (r) => r.concepts ?? null,
        render: (r) => txt(r.concepts),
      },
      {
        key: 'evidence',
        title: '证据',
        value: (r) => r.evidence ?? null,
        render: (r) => txt(r.evidence),
      },
    ],
    [],
  )

  const option = useMemo<EChartsOption>(
    () => ({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 96, right: 24, top: 16, bottom: 24 },
      xAxis: {
        type: 'value',
        name: '关联度',
        axisLabel: { color: CHART.ink2 },
        splitLine: { lineStyle: { color: CHART.line } },
      },
      yAxis: {
        type: 'category',
        data: entries.map((e) => txt(e.name)),
        axisLabel: { color: CHART.ink2 },
        axisLine: { lineStyle: { color: CHART.line } },
      },
      series: [
        {
          type: 'bar',
          data: entries.map((e) => ({
            value: typeof e.score === 'number' && Number.isFinite(e.score) ? e.score : null,
            itemStyle: { color: directionColor(e.dir_color) },
          })),
        },
      ],
    }),
    [entries],
  )

  return (
    <div className="space-y-4">
      <Card title="政策原文详情">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="原文发布日期" value={txt(p?.publish_date)} sub="数据原文日期，非抓取时间" />
          <Stat label="抓取时间" value={txt(p?.crawled_at)} sub="与发布日期语义分离" />
          <Stat label="发文机关" value={txt(p?.issuing_body)} />
          <Stat label="文号" value={txt(p?.doc_number)} />
        </div>
        <div className="mt-3 text-body text-sf-ink">
          <span className="text-sf-ink-3">标题：</span>
          {txt(p?.title)}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-label text-sf-ink-3">
          <span>来源：{txt(p?.source)}</span>
          <span>正文来源：{txt(p?.body_source)}</span>
          <FreshnessBadge level={freshnessOf(p?.is_fresh)} />
        </div>
        <details className="mt-3 rounded-tile border border-sf-line bg-sf-surface-2 px-3.5 py-2">
          <summary className="cursor-pointer text-body text-sf-ink-2">政策正文（原文，点击展开）</summary>
          <div className="mt-2 whitespace-pre-wrap text-body text-sf-ink-2">{txt(p?.body_text)}</div>
        </details>
        <div className="mt-2 text-label">
          {p?.source_url ? (
            <a href={p.source_url} target="_blank" rel="noreferrer" className="text-sf-accent hover:underline">
              查看原文链接
            </a>
          ) : (
            <span className="text-sf-ink-3">原文链接：—</span>
          )}
        </div>
      </Card>

      <Card title="传导链：标的 × 关联度">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <Stat label="命中行业" value={num(sectors.length)} />
          <Stat label="关联标的" value={num(entries.length)} />
          <Stat label="相关概念" value={num(conceptsHit.length)} />
          <Stat label="未展开行业" value={num(membersUnavailable.length)} />
        </div>

        {sectors.length > 0 && (
          <p className="mb-3 text-xs text-sf-ink-3">
            命中行业（本地关键词派生）：
            {sectors
              .map(
                (s) =>
                  `${txt(s.name)}（${txt(s.matched_by)}，${num(s.stock_codes_count)} 只${s.derived ? '，derived' : ''}）`,
              )
              .join('；')}
          </p>
        )}

        <CollapsibleRankTable
          title="标的关联度排行"
          rows={entries}
          rowKey={(r, i) => `${r.code ?? 'na'}-${i}`}
          columns={columns}
          defaultSort={{ key: 'score', dir: 'desc' }}
          barColor={(r) => directionColor(r.dir_color)}
          hint="关联度 = 文本共现（概念命中 ×1；个股与概念同标题点名 ×3），不是收益预测；方向为文本情绪启发式五档，配色取自后端 dir_color。"
        />

        {entries.length > 0 && (
          <div className="mt-3">
            <EChart
              option={option}
              height={Math.max(180, entries.length * 32)}
              ariaLabel="政策传导标的关联度条形图（文本共现统计，非收益预测）"
            />
          </div>
        )}
        {entries.length === 0 && (
          <p className="mt-3 text-body text-sf-ink-3">
            本次没有可展开的关联标的（命中行业可能取不到成分股，已列入下方 members_unavailable，未编造成分股）。
          </p>
        )}
      </Card>

      <Card title="方法与诚实说明">
        <div className="space-y-2 text-label text-sf-ink-3">
          <div>
            <span className="text-sf-ink-2">口径（basis）：</span>
            {txt(data.basis)}
          </div>
          <div>
            <span className="text-sf-ink-2">免责声明（disclaimer）：</span>
            {txt(data.disclaimer)}
          </div>
          <div>
            <span className="text-sf-ink-2">派生说明（derived_note）：</span>
            {txt(data.derived_note)}
          </div>
          {membersUnavailable.length > 0 && (
            <div>
              <div className="text-sf-ink-2">未展开成分股的命中行业（原样，未编造标的）：</div>
              <pre className="mt-1 overflow-x-auto rounded-tile border border-sf-line bg-sf-surface-2 p-2 text-[11px] text-sf-ink-3">
                {membersUnavailable.map((m) => (typeof m === 'string' ? m : JSON.stringify(m))).join('\n')}
              </pre>
            </div>
          )}
          {rawList(data.unavailable).length > 0 && (
            <div>不可用：{rawList(data.unavailable).join('、')}</div>
          )}
        </div>
      </Card>
    </div>
  )
}

function SectorCoverage({ data }: { data: SectorMap | undefined }) {
  const stats: Record<string, unknown> = data?.stats ?? {}
  const items = data?.items ?? []

  return (
    <Card title="行业映射覆盖">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="映射总数" value={num(stats.total)} />
        <Stat label="ok" value={num(stats.ok)} />
        <Stat label="failed" value={num(stats.failed)} />
        <Stat label="stale" value={num(stats.stale)} />
        <Stat label="精编行业" value={num(stats.manual_sectors)} />
      </div>
      <p className="mt-3 text-xs text-sf-ink-3">
        keywords 来源：L0 = 板块名本身；L1 = 内置少量常见同义词（rule_l0 / rule_l1），非 LLM 全量精编。
        fetch_status=failed 或 member_count=0 的行业不展开成分股、不编造标的。
        {data?.note ? ` ${data.note}` : ''}
      </p>
      {items.length > 0 && (
        <details className="mt-3 rounded-tile border border-sf-line bg-sf-surface-2 px-3.5 py-2">
          <summary className="cursor-pointer text-body text-sf-ink-2">映射明细（{items.length}）</summary>
          <ul className="mt-2 space-y-1 text-label text-sf-ink-3">
            {items.slice(0, 20).map((s, i) => (
              <li key={`${s.board_name ?? 'na'}-${i}`}>
                {txt(s.board_name)} · {txt(s.fetch_status)} · {txt(s.source)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  )
}
