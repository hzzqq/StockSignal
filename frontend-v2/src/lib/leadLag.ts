/**
 * 维度领先-滞后矩阵（v1 `66_维度领先滞后矩阵.py` / `modules/lead_lag_matrix.py` 的 v2 实现）。
 *
 * 与 v1 对齐的口径：
 *  - 只用离线可靠广度维度 REAL_FEATURES（涨跌/平家数、涨停/跌停家数、红盘占比）；
 *    连板梯队类维度离线缺真值，一律剔除，不进入相关计算、不编造。
 *  - 对每一对**有序** (i, j)，在 lag 0..20 上取 |corr| 最大者；
 *    lag=k 表示「i 取 t 日、j 取 t+k 日」，即 i 领先 j k 个交易日。
 *    结果与 v1 matrix[i][j] 一致：正相关记 +k（同向领先），负相关记 -k（反向领先）。
 *  - 皮尔逊相关本身就是 z-score 归一后的协方差，与 v1 显式 z-score 在数学上等价。
 *  - 互相关只描述协同/错位，**非因果、非预测**。
 *
 * 与 v1 的差异（如实声明，不伪装 1:1 复刻）：
 *  - v2 每维度要求 ≥30 个有效交易日、每个 lag 要求 ≥30 个成对样本；
 *    v1 闸门是「非空率 ≥20% + 变异系数 + 每 lag ≥3 样本」。v2 更严格，
 *    样本不足的维度与维度对**如实列出**，绝不静默消失、绝不补 0。
 *  - v1 输出 n×n 热力图；v2 输出有序对明细表（额外带出 corr、成对样本、样本区间）。
 */
import type { BreadthHistoryPoint } from '@/api/schemas/read'

export interface Dimension {
  key: string
  label: string
}

/** 与 v1 modules/breadth_features.py::REAL_FEATURES 逐项一致；连板梯队类字段刻意不列入。 */
export const DIMENSIONS: readonly Dimension[] = [
  { key: 'up_count', label: '上涨家数' },
  { key: 'down_count', label: '下跌家数' },
  { key: 'flat_count', label: '平盘家数' },
  { key: 'limit_up', label: '涨停家数' },
  { key: 'limit_down', label: '跌停家数' },
  { key: 'red_ratio', label: '红盘占比' },
]

/** 明确列出被数据闸门剔除的字段，供 UI 如实说明「哪些没算、为什么没算」。 */
export const EXCLUDED_DIMENSIONS = [
  { key: 'connect_hl', label: '连板高度' },
  { key: 'connect_2b', label: '连板家数≥2板' },
  { key: 'zt_fail_ratio', label: '炸板率' },
  { key: 'fc_ratio', label: '平均封成比' },
  { key: 'zt_prev_ret', label: '昨日涨停表现' },
  { key: 'touch_down', label: '倒跌停家数' },
]

/**
 * v1 66 页明确披露的机械相关：红盘占比由涨跌平家数直接派生，
 * 因此它与涨跌家数族之间的领先/滞后部分不是独立信息。
 */
export const DERIVED_NOTICE =
  '红盘占比由上涨/下跌/平盘家数直接派生（red_ratio = 上涨 /(上涨+下跌+平盘)），' +
  '故 up/down/flat 与 red_ratio 之间的领先-滞后部分属于机械相关；' +
  '真正有信息量的信号在「涨跌家数族」与「涨停/跌停家数（极限宽度）」之间。'

export const MIN_SAMPLES = 30
export const MIN_PAIR_SAMPLES = 30
export const MAX_LAG = 20

/** 逐日取值；null / NaN / 非数字一律为 null，绝不补 0。 */
export function valuesOf(series: BreadthHistoryPoint[], key: string): (number | null)[] {
  return series.map((row) => {
    const v = (row as Record<string, unknown>)[key]
    return typeof v === 'number' && Number.isFinite(v) ? v : null
  })
}

export function validCount(values: readonly (number | null)[]): number {
  // 防御性：外部直接传入 NaN / Infinity 时也不能算作有效样本（valuesOf 已过滤，这里是第二道闸）。
  return values.reduce<number>((n, v) => n + (typeof v === 'number' && Number.isFinite(v) ? 1 : 0), 0)
}

/** 近乎常数（无信息）闸门，对齐 v1 usable_dims 的变异系数检查。 */
export function isNearConstant(values: readonly (number | null)[]): boolean {
  const nums = values.filter((v): v is number => v !== null)
  if (nums.length < 2) return true
  const mean = nums.reduce((s, v) => s + v, 0) / nums.length
  const sd = Math.sqrt(nums.reduce((s, v) => s + (v - mean) ** 2, 0) / nums.length)
  return sd <= 1e-6 * Math.max(1, Math.abs(mean))
}

/** 皮尔逊相关；样本不足或任一方差为 0 返回 null（不造数）。 */
export function pearson(a: readonly number[], b: readonly number[], minSamples = MIN_PAIR_SAMPLES): number | null {
  if (a.length !== b.length || a.length < minSamples) return null
  const n = a.length
  let sa = 0
  let sb = 0
  for (let i = 0; i < n; i++) {
    sa += a[i]
    sb += b[i]
  }
  const ma = sa / n
  const mb = sb / n
  let num = 0
  let da = 0
  let db = 0
  for (let i = 0; i < n; i++) {
    const x = a[i] - ma
    const y = b[i] - mb
    num += x * y
    da += x * x
    db += y * y
  }
  if (da <= 0 || db <= 0) return null
  const r = num / Math.sqrt(da * db)
  return Number.isFinite(r) ? Math.max(-1, Math.min(1, r)) : null
}

export interface LeadLagResult {
  x: string
  y: string
  xLabel: string
  yLabel: string
  /** i 领先 j 的交易日数（非负）；0 表示同步 */
  lag: number
  /** 带符号相关系数：v1 据此把 matrix[i][j] 记成 +k 或 -k */
  corr: number
  samples: number
  /** 实际参与比较的 lag 个数（样本不足的 lag 会被跳过，不静默） */
  evaluatedLags: number
}

/** v1 matrix[i][j] 的带符号 lag：正相关 +k，负相关 -k。 */
export function signedLag(r: LeadLagResult): number {
  // lag=0 时统一返回 +0：否则负相关会产出 -0，表格/类型判断都容易踩 Object.is 坑。
  if (r.lag === 0) return 0
  return r.corr >= 0 ? r.lag : -r.lag
}

/** 对有序对 (x, y) 在 lag 0..maxLag 上找 |corr| 最大者。 */
export function bestLag(
  xs: readonly (number | null)[],
  ys: readonly (number | null)[],
  x: Dimension,
  y: Dimension,
  maxLag = MAX_LAG,
): LeadLagResult | null {
  let best: LeadLagResult | null = null
  let evaluated = 0
  for (let lag = 0; lag <= maxLag; lag++) {
    const a: number[] = []
    const b: number[] = []
    for (let t = 0; t + lag < xs.length; t++) {
      const xv = xs[t]
      const yv = ys[t + lag]
      if (xv !== null && yv !== null) {
        a.push(xv)
        b.push(yv)
      }
    }
    const r = pearson(a, b)
    if (r === null) continue
    evaluated += 1
    if (!best || Math.abs(r) > Math.abs(best.corr)) {
      best = {
        x: x.key, y: y.key, xLabel: x.label, yLabel: y.label,
        lag, corr: r, samples: a.length, evaluatedLags: evaluated,
      }
    }
  }
  if (best) best.evaluatedLags = evaluated
  return best
}

export interface ExcludedDimension {
  key: string
  label: string
  samples: number
  reason: string
}

export interface SkippedPair {
  x: string
  y: string
  xLabel: string
  yLabel: string
  reason: string
}

export interface MatrixOutput {
  /** 全部有序对 i≠j（与 v1 n×n 矩阵的单元格一一对应，去掉对角线） */
  rows: LeadLagResult[]
  /** 样本不足 / 近乎常数被剔除的可靠维度（如实展示，不静默消失） */
  excluded: ExcludedDimension[]
  /** 因成对样本不足或方差为 0 未产出结果的维度对（如实展示，不静默消失） */
  skippedPairs: SkippedPair[]
  firstDate: string | null
  lastDate: string | null
  totalDays: number
  usableDays: number
}

export function buildMatrix(series: BreadthHistoryPoint[], maxLag = MAX_LAG): MatrixOutput {
  const sorted = [...series].sort((a, b) => String(a.date).localeCompare(String(b.date)))
  const firstDate = sorted.length ? String(sorted[0].date) : null
  const lastDate = sorted.length ? String(sorted[sorted.length - 1].date) : null
  const usableDays = sorted.reduce((n, row) => {
    const rec = row as Record<string, unknown>
    return n + (DIMENSIONS.some((d) => typeof rec[d.key] === 'number' && Number.isFinite(rec[d.key]))
      ? 1 : 0)
  }, 0)

  const usable: Dimension[] = []
  const excluded: ExcludedDimension[] = []
  const data = new Map<string, (number | null)[]>()
  for (const d of DIMENSIONS) {
    const v = valuesOf(sorted, d.key)
    const n = validCount(v)
    if (n < MIN_SAMPLES) {
      excluded.push({ key: d.key, label: d.label, samples: n, reason: `有效样本 ${n} 日 < ${MIN_SAMPLES} 日` })
      continue
    }
    if (isNearConstant(v)) {
      excluded.push({ key: d.key, label: d.label, samples: n, reason: '近乎常数（无信息）' })
      continue
    }
    usable.push(d)
    data.set(d.key, v)
  }

  const rows: LeadLagResult[] = []
  const skippedPairs: SkippedPair[] = []
  for (let i = 0; i < usable.length; i++) {
    for (let j = 0; j < usable.length; j++) {
      if (i === j) continue
      const x = usable[i]
      const y = usable[j]
      const r = bestLag(data.get(x.key) ?? [], data.get(y.key) ?? [], x, y, maxLag)
      if (r) {
        rows.push(r)
      } else {
        skippedPairs.push({
          x: x.key, y: y.key, xLabel: x.label, yLabel: y.label,
          reason: `所有 lag 的成对样本均 < ${MIN_PAIR_SAMPLES} 或方差为 0`,
        })
      }
    }
  }
  return { rows, excluded, skippedPairs, firstDate, lastDate, totalDays: sorted.length, usableDays }
}
