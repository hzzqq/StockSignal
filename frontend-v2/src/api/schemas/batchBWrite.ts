import { z } from 'zod'

/**
 * parity B 批次两个写端点的入参 / 响应契约：
 *   PUT /api/v2/read/user-dashboard  body { widgets: string[] }  -> data { widgets: string[] }
 *   PUT /api/v2/read/review-notes    body { date, content }      -> data { date, content }
 * 与统一写层 apiMutate + useWriteMutation 配套使用；后端才是真理源，入参 schema
 * 在调用方发出请求前先挡住非法值，响应 schema 严格解包（catchall 收新增字段）。
 */

/** user-dashboard 合法 widget key：对齐 v2 页面真实组件 id（DashboardCustom.tsx），精确 5 个。 */
export const USER_DASHBOARD_WIDGET_KEYS = [
  'snapshot',
  'recommendation',
  'breadth',
  'event',
  'backtest',
] as const
export type UserDashboardWidgetKey = (typeof USER_DASHBOARD_WIDGET_KEYS)[number]

/**
 * 真实日历校验（非仅正则）：2026-02-30 / 2026-13-01 必须非法。
 * `new Date(<固定字符串>)` 是解析校验，不是取运行时 now，不违反 honest-data 守卫。
 */
export function isValidCalendarDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false
  const d = new Date(`${s}T00:00:00Z`)
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s
}

/** 入参：白名单 5 个 id，长度 1–5、不重复，保序。 */
export const UserDashboardWriteSchema = z.object({
  widgets: z
    .array(z.enum(USER_DASHBOARD_WIDGET_KEYS))
    .min(1, 'widgets 至少 1 项')
    .max(5, 'widgets 最多 5 项')
    .refine((arr) => new Set(arr).size === arr.length, 'widgets 不能重复'),
})
export type UserDashboardWrite = z.infer<typeof UserDashboardWriteSchema>

/** 响应：echo 入参顺序，用 string[] 收，不臆造白名单外的约束。 */
export const UserDashboardDataSchema = z
  .object({
    widgets: z.array(z.string()),
  })
  .catchall(z.unknown())
export type UserDashboardData = z.infer<typeof UserDashboardDataSchema>

/** 入参：date 真实日历校验；content ≤500000 字符（后端 _REVIEW_MAX_CHARS），空串允许。 */
export const ReviewNotesWriteSchema = z.object({
  date: z.string().refine(isValidCalendarDate, 'date 须为真实 YYYY-MM-DD'),
  content: z.string().max(500000, 'content 不得超过 500000 字符'),
})
export type ReviewNotesWrite = z.infer<typeof ReviewNotesWriteSchema>

/** 响应：原文回显。 */
export const ReviewNotesDataSchema = z
  .object({
    date: z.string(),
    content: z.string(),
  })
  .catchall(z.unknown())
export type ReviewNotesData = z.infer<typeof ReviewNotesDataSchema>
