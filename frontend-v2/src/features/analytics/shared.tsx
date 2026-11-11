import type { ReactNode } from 'react'
import type { BreadthAnalytics } from '@/api/schemas/read'
import { Card } from '@/shared/ui/Card'
import { EmptyState } from '@/shared/ui/States'

/**
 * 65/67/68/69 四页共享骨架（v2 native）。
 *
 * 诚实红线（与 v1 四页一致、后端 /breadth-analytics 同源）：
 *  - 数据日取端点 data_as_of（权威数据日），绝不显示 now()；
 *  - 每段统计独立 available；不可用只让该段显「暂无」+ reason，绝不补零/编造；
 *  - OFFLINE_MISSING 的 10 个维度逐条列出、绝不进入任何计算；
 *  - 全部结论标注「历史描述、不预测收益」。
 */

export interface AnalyticsSectionLike {
  available: boolean
  reason?: string | null
}

/** 缺失一律显「—」；0 是真实数值，不能被当成缺失。 */
export function show(v: number | string | null | undefined, suffix = ''): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number' && !Number.isFinite(v)) return '—'
  return `${v}${suffix}`
}

/** 历史分位（0~1）转百分数；缺失显「—」。 */
export function showPct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

/** 浮点数值按固定小数位展示；缺失显「—」，不四舍五入成 0。 */
export function showNum(v: number | null | undefined, digits = 2, suffix = ''): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${v.toFixed(digits)}${suffix}`
}

export function AnalyticsHeader({
  title,
  caption,
  data,
}: {
  title: string
  caption: string
  data?: BreadthAnalytics
}) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-xs text-sf-ink-3 mt-1">{caption}</p>
      <p className="text-xs text-sf-ink-3 mt-1">
        {`数据截至 ${data?.data_as_of ?? '—'}（离线健康镜像快照，非实时行情）。全部为历史统计描述，不预测收益、不构成买卖建议。`}
      </p>
    </div>
  )
}

/** 单段独立降级：该段 unavailable 时只影响该段，其余段照常渲染。 */
export function SectionState({
  section,
  label,
  children,
}: {
  section: AnalyticsSectionLike | undefined
  label: string
  children: ReactNode
}) {
  if (!section || !section.available) {
    return (
      <EmptyState
        label={`${label}暂无数据`}
        hint={section?.reason ?? '该段统计不可用（其余段不受影响）'}
      />
    )
  }
  return <>{children}</>
}

const MISSING_NOTE =
  '离线健康镜像中这些维度或为 NaN、或被填 0（并非真值），本页不引用、不补零、不参与任何距离/分位/z-score 计算。'

/** 四页统一的数据边界说明：可靠字段枚举 + 10 个缺真值维度逐条披露。 */
export function DataBoundary({
  data,
  method,
  extra,
}: {
  data: BreadthAnalytics
  method: string
  extra?: string
}) {
  const reliable = Object.values(data.reliable_labels)
  const missing = Object.entries(data.offline_missing)
  return (
    <Card title="离线数据边界（务必阅读）">
      <p className="text-xs text-sf-ink-2">
        本页仅使用离线可靠广度字段（{reliable.length} 个）：{reliable.join('、')}。
      </p>
      <details className="mt-2 text-xs text-sf-ink-2">
        <summary className="cursor-pointer text-sf-ink-3">
          以下 {missing.length} 个维度离线缺真值，一律剔除、不编造
        </summary>
        <ul className="mt-2 space-y-1">
          {missing.map(([k, v]) => (
            <li key={k}>
              <span className="font-mono text-sf-ink-3">{k}</span> — {v}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-sf-ink-3">{MISSING_NOTE}</p>
      </details>
      {extra && <p className="mt-2 text-xs text-sf-ink-2">{extra}</p>}
      <p className="mt-2 text-xs text-sf-ink-3">📐 方法学：{method}</p>
      <p className="mt-1 text-xs text-sf-ink-3">{data.note}</p>
    </Card>
  )
}
