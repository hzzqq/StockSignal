/**
 * 新鲜度可视化工具（PLAN.md §5 红线）。
 *
 * 重要：本模块**只计算「可见化标签」**，绝不重算仓位或任何决策规则。
 * 仓位真理源唯一在后端 `modules/decision.derive_position`，前端禁止复制。
 * 新鲜度口径以本仓常量对齐：
 *   FRESH_WARN_DAYS = 4  → 超过即「偏旧」
 *   FRESH_STALE_DAYS = 8 → 超过即「陈旧」（对应后端封顶 40% 的同一数据日边界）
 * 判定基于**权威数据日**（快照自带的 date / data_age_days），不用 now() 兜底。
 */

export type FreshnessLevel = 'ok' | 'warn' | 'stale' | 'unknown'

/** 与后端 modules/decision 同源常量（仅用于 UI 标注，不参与决策计算）。 */
export const FRESH_WARN_DAYS = 4
export const FRESH_STALE_DAYS = 8

/** 由数据滞后天数推导可见化等级（权威数据日 → 今日差）。 */
export function freshnessLevelFromAge(ageDays: number | undefined | null): FreshnessLevel {
  if (ageDays == null || Number.isNaN(ageDays)) return 'unknown'
  if (ageDays < 0) return 'unknown'
  if (ageDays <= FRESH_WARN_DAYS) return 'ok'
  if (ageDays <= FRESH_STALE_DAYS) return 'warn'
  return 'stale'
}

/** 由后端 data_freshness.status 字符串推导等级（ok/warn/stale）。 */
export function freshnessFromStatus(status?: string): FreshnessLevel {
  if (!status) return 'unknown'
  const s = status.toLowerCase()
  if (s === 'ok') return 'ok'
  if (s === 'warn' || s === 'warning') return 'warn'
  if (s === 'stale') return 'stale'
  return 'unknown'
}

/** 等级 → 中文标签（UI 展示）。 */
export function freshnessLabel(level: FreshnessLevel): string {
  switch (level) {
    case 'ok':
      return '数据新鲜'
    case 'warn':
      return '数据偏旧'
    case 'stale':
      return '数据陈旧'
    default:
      return '新鲜度未知'
  }
}
