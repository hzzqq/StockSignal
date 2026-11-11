import { z } from 'zod'
import { useQuery } from '@tanstack/react-query'
import raw from './data/constructionDiag.json'

/**
 * P1 组合构建诊断 · 只读载荷 schema（对应 data/constructionDiag.json）。
 *
 * 数据来源：P1 回测引擎（src/backtest/engine.py）在 pred_ens_v39gru_w025_h10 上的
 * 只读复算快照（2026-11-09 数据，2026-11-11 导出）。本文件不发起网络请求、
 * 不读写任何端点，直接校验本地随包 JSON——与 v2「离线优先 / 诚实红线」一致。
 *
 * 红线：解析失败即抛错（不兜底），由页面 QueryState 渲染错误态；数值可空处显式 nullable，
 * 绝不 `?? 0`。
 */

export const ConstructionDiagSchema = z.object({
  meta: z.object({
    generated_at: z.string(),
    model: z.string(),
    pred_source: z.string(),
    horizon: z.number().nullable().optional(),
    top_pct: z.number().nullable().optional(),
    date_range: z.array(z.string()).optional(),
    note: z.string(),
  }),
  curves: z.object({
    idx_2026: z.number(),
    dates: z.array(z.string()),
    long_only_net: z.array(z.number()),
    long_short_net: z.array(z.number()),
    benchmark_gross: z.array(z.number()),
  }),
  headline: z.object({
    rf: z.number(),
    buffer: z.number(),
    pure_long: z.object({
      full_return: z.number(),
      full_sharpe: z.number(),
      y2026_return: z.number(),
      y2026_sharpe: z.number(),
    }),
    market_neutral: z.object({
      full_return: z.number(),
      full_sharpe: z.number(),
      y2024_return: z.number(),
      y2026_return: z.number(),
      y2026_sharpe: z.number(),
    }),
  }),
  turnover_free_lunch: z.object({
    label: z.string(),
    market_neutral: z.object({
      buffer0_turnover: z.number(),
      buffer0_full_return: z.number(),
      buffer01_turnover: z.number(),
      buffer01_full_return: z.number(),
      buffer01_y2026_return: z.number(),
    }),
    pure_long: z.object({
      buffer0_full_return: z.number(),
      buffer01_full_return: z.number(),
    }),
    note: z.string(),
  }),
  rf_sweep: z.array(
    z.object({
      rf: z.number(),
      y2026_market_neutral_return: z.number(),
      y2026_market_neutral_sharpe: z.number(),
    }),
  ),
  alpha_decay: z.array(
    z.object({
      window: z.string(),
      excess_total_return: z.number(),
      excess_end: z.number().nullable().optional(),
    }),
  ),
  conclusions: z.array(z.string()),
  honesty: z.string(),
})

export type ConstructionDiag = z.infer<typeof ConstructionDiagSchema>

/**
 * 本地随包 JSON 经 Zod 严格校验后返回。queryFn 内校验→失败时 QueryState 渲染错误态，
 * 不静默兜底。staleTime=Infinity：静态快照无需刷新。
 */
export function useConstructionDiag() {
  return useQuery({
    queryKey: ['construction-diag'],
    queryFn: () => ConstructionDiagSchema.parse(raw as unknown),
    staleTime: Infinity,
  })
}
