import { z } from 'zod'

/**
 * 只读端点响应 schema（W1 后端 /api/v2/read/*）。
 *
 * 字段以本仓真实数据文件（`data/daily_snapshot.json` / `snapshots/*.json` /
 * `p1_signals/signal_*.json` / `paper_*.json` 等）2026-11-06 真扫得到的结构为准，
 * 不臆造字段名。深度嵌套且前端不逐一渲染的容器用 `z.record` / `z.unknown()` 兜底，
 * 但凡渲染到的字段都显式声明类型。缺失文件 → 信封返回 status=error，前端判空渲染「无数据」。
 *
 * 红线（PLAN.md §4.3 / §5）：解析失败即抛错，禁止 `?? 0` / 默认值兜底。
 */

// ───────── 决策快照（daily_snapshot / snapshots/<date>）─────────
export const PositionSchema = z.object({
  pct: z.number(),
  band: z.string(),
  color: z.string(),
  reasons: z.array(z.string()).default([]),
})
export type Position = z.infer<typeof PositionSchema>

export const EventFactorSchema = z.object({
  available: z.boolean().optional(),
  long_count: z.number().optional(),
  adj: z.number().optional(),
  as_of: z.string().optional(),
})
export type EventFactor = z.infer<typeof EventFactorSchema>

export const DataFreshnessSourceSchema = z.object({
  as_of: z.string().optional(),
  lag_days: z.number().optional(),
  status: z.string().optional(),
})
export type DataFreshnessSource = z.infer<typeof DataFreshnessSourceSchema>

export const DataFreshnessSchema = z.object({
  status: z.string().optional(),
  max_lag_days: z.number().optional(),
  sources: z.record(z.string(), DataFreshnessSourceSchema).optional(),
})
export type DataFreshness = z.infer<typeof DataFreshnessSchema>

export const ScenarioSchema = z.object({
  name: z.string().optional(),
  prob: z.number().optional(),
  color: z.string().optional(),
  desc: z.string().optional(),
  trigger: z.string().optional(),
})
export type Scenario = z.infer<typeof ScenarioSchema>

export const LadderSchema = z.object({
  distribution: z.array(z.array(z.unknown())).optional(),
  max_boards: z.number().optional(),
  total_connect: z.number().optional(),
})
export type Ladder = z.infer<typeof LadderSchema>

/** 指标字典：键为指标名，值为数值（含 null，缺失即 null 不补零）。 */
export const IndicatorsSchema = z.record(z.string(), z.unknown()).optional()
export type Indicators = z.infer<typeof IndicatorsSchema>

export const DailySnapshotSchema = z.object({
  date: z.string(),
  as_of: z.string().optional(),
  data_age_days: z.number().optional(),
  generated_at: z.string().optional(),
  temperature: z.number().optional(),
  cycle: z.string().optional(),
  score: z.number().optional(),
  bias: z.string().optional(),
  confidence: z.number().optional(),
  promo_overall: z.number().optional(),
  ladder: LadderSchema.optional(),
  position: PositionSchema.optional(),
  event_factor: EventFactorSchema.optional(),
  data_freshness: DataFreshnessSchema.optional(),
  indicators: IndicatorsSchema,
  signals: z.array(z.unknown()).optional(),
  scenario: z.array(ScenarioSchema).optional(),
})
export type DailySnapshot = z.infer<typeof DailySnapshotSchema>

// ───────── P1 量化信号（p1_signals/signal_*.json）─────────
export const P1TopItemSchema = z.object({
  symbol: z.string(),
  pred: z.number().optional(),
  rank: z.number().optional(),
})
export type P1TopItem = z.infer<typeof P1TopItemSchema>

export const P1SignalSchema = z.object({
  generated_at: z.string().optional(),
  latest_date: z.string().optional(),
  top_long: z.array(P1TopItemSchema).optional(),
  top_short: z.array(P1TopItemSchema).optional(),
  daily: z.unknown().optional(),
  model: z.unknown().optional(),
  horizon: z.unknown().optional(),
})
export type P1Signal = z.infer<typeof P1SignalSchema>

// ───────── 每日荐股（daily_recommendation.json，可能 unavailable）─────────
export const DailyRecommendationSchema = z
  .object({
    status: z.string().optional(),
    reason: z.string().optional(),
    generated_at: z.string().optional(),
    disclaimer: z.string().optional(),
  })
  .catchall(z.unknown())
export type DailyRecommendation = z.infer<typeof DailyRecommendationSchema>

// ───────── 虚拟用户模拟（reports/virtual_users_sim.json）─────────
export const VirtualUsersSimSchema = z
  .object({
    meta: z.record(z.string(), z.unknown()).optional(),
    aggregate: z.unknown().optional(),
    profiles: z.unknown().optional(),
  })
  .catchall(z.unknown())
export type VirtualUsersSim = z.infer<typeof VirtualUsersSimSchema>

// ───────── 模拟交易账本（paper_<user>.json）─────────
export const PaperPositionSchema = z.object({
  name: z.string().optional(),
  qty: z.number().optional(),
  avg_cost: z.number().optional(),
})
export type PaperPosition = z.infer<typeof PaperPositionSchema>

export const PaperTradeRowSchema = z.object({
  time: z.string().optional(),
  code: z.string().optional(),
  name: z.string().optional(),
  side: z.string().optional(),
  price: z.number().optional(),
  qty: z.number().optional(),
  amount: z.number().optional(),
})
export type PaperTradeRow = z.infer<typeof PaperTradeRowSchema>

export const PaperTradeSchema = z.object({
  init_cash: z.number().optional(),
  cash: z.number().optional(),
  positions: z.record(z.string(), PaperPositionSchema).optional(),
  trades: z.array(PaperTradeRowSchema).optional(),
  equity: z.array(z.array(z.unknown())).optional(),
})
export type PaperTrade = z.infer<typeof PaperTradeSchema>

// ───────── 复盘笔记（review_notes_<date>.md 包装）─────────
export const ReviewNotesSchema = z.object({
  date: z.string(),
  content: z.string(),
})
export type ReviewNotes = z.infer<typeof ReviewNotesSchema>

// ───────── 网页作品集（webapps/*/meta.json）─────────
export const WebAppSchema = z.object({
  dir: z.string(),
  title: z.string(),
  desc: z.string().optional(),
  entry: z.string(),
  version: z.string().optional(),
  added: z.string().optional(),
})
export type WebApp = z.infer<typeof WebAppSchema>

// ───────── 归档日期清单 ─────────
export const SnapshotDateListSchema = z.array(z.string())
export type SnapshotDateList = z.infer<typeof SnapshotDateListSchema>
