import { toFiniteNumber } from './common'

/**
 * K 线 / 分时的行解析与指标计算（纯函数，可单测）。
 *
 * 诚实红线：
 *  - 后端 rows 为 `Record<string, unknown>` 透传，数值可能缺失（后端 _sanitize 把 NaN/Inf 洗成 null）。
 *    缺失一律按 null 处理，**绝不补 0**。
 *  - MA / MACD 前若干根因样本不足 → null（ECharts 断线），**绝不补 0**。
 *  - 计算只使用**连续**的有效样本：EMA 链遇 null 即断链，需重新攒够样本才继续。
 */

/** 单根 K 线（缺失值保留为 null，不做填充）。 */
export interface KlineBar {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
}

/** 单个分时点（缺失值保留为 null）。 */
export interface IntradayPoint {
  /** 原始 time 字段（后端透传，如 '2026-11-06 09:30:00'）。 */
  time: string
  /** 轴标签 'HH:MM'；无法解析时回退为原始字符串。 */
  label: string
  close: number | null
  volume: number | null
  amount: number | null
}

function str(v: unknown): string | null {
  if (typeof v === 'string') return v
  if (typeof v === 'number' && Number.isFinite(v)) return String(v)
  return null
}

/** 解析 K 线行：date 缺失的行直接丢弃（无法定位到时间轴），其余缺失值保留 null。 */
export function parseKlineRows(rows: Record<string, unknown>[]): KlineBar[] {
  const out: KlineBar[] = []
  for (const r of rows) {
    const date = str(r.date)
    if (!date) continue
    out.push({
      date,
      open: toFiniteNumber(r.open),
      high: toFiniteNumber(r.high),
      low: toFiniteNumber(r.low),
      close: toFiniteNumber(r.close),
      volume: toFiniteNumber(r.volume),
    })
  }
  return out
}

/** 解析分时行：time 缺失的行丢弃（无法定位到时间轴）。 */
export function parseIntradayRows(rows: Record<string, unknown>[]): IntradayPoint[] {
  const out: IntradayPoint[] = []
  for (const r of rows) {
    const time = str(r.time)
    if (!time) continue
    out.push({
      time,
      label: intradayLabel(time),
      close: toFiniteNumber(r.close),
      volume: toFiniteNumber(r.volume),
      amount: toFiniteNumber(r.amount),
    })
  }
  return out
}

/** '2026-11-06 09:30:00' → '09:30'；'09:30' → '09:30'；无法解析则原样返回。 */
export function intradayLabel(time: string): string {
  const m = time.match(/(\d{1,2}:\d{2})/)
  return m ? m[1] : time
}

/**
 * 简单移动平均：窗口内任一值缺失 → 该点 null（断线，不补 0）。
 * 前 window-1 根样本不足 → null。
 */
export function rollingMean(values: (number | null)[], window: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  if (window <= 0) return out
  for (let i = window - 1; i < values.length; i++) {
    let sum = 0
    let ok = true
    for (let j = i - window + 1; j <= i; j++) {
      const v = values[j]
      if (v === null) {
        ok = false
        break
      }
      sum += v
    }
    if (ok) out[i] = sum / window
  }
  return out
}

/**
 * EMA（通达信口径：首值取前 period 个样本的 SMA，其后 Y=(2X+(N-1)Y')/(N+1)）。
 *
 * 诚实红线：样本不足 period 个 → null；序列中遇 null → **断链**（prev 归零），
 * 需重新攒够 period 个连续样本才重新出值，绝不跨缺口臆造。
 */
export function emaSeries(values: (number | null)[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  if (period <= 0) return out
  const k = 2 / (period + 1)
  let prev: number | null = null
  let sum = 0
  let count = 0
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (v === null) {
      prev = null
      sum = 0
      count = 0
      continue
    }
    if (prev === null) {
      sum += v
      count += 1
      if (count === period) {
        prev = sum / period
        out[i] = prev
      }
      continue
    }
    prev = v * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

/** MACD 三件套。 */
export interface MacdResult {
  /** DIF = EMA12 − EMA26 */
  dif: (number | null)[]
  /** DEA = EMA9(DIF) */
  dea: (number | null)[]
  /** MACD 柱 = 2 × (DIF − DEA)（通达信口径） */
  hist: (number | null)[]
}

export function macdSeries(closes: (number | null)[], fast = 12, slow = 26, signal = 9): MacdResult {
  const emaFast = emaSeries(closes, fast)
  const emaSlow = emaSeries(closes, slow)
  const dif: (number | null)[] = closes.map((_, i) => {
    const f = emaFast[i]
    const s = emaSlow[i]
    return f === null || s === null ? null : f - s
  })
  const dea = emaSeries(dif, signal)
  const hist: (number | null)[] = dif.map((d, i) => {
    const e = dea[i]
    return d === null || e === null ? null : 2 * (d - e)
  })
  return { dif, dea, hist }
}

/**
 * 分时均价（累计成交额 / 累计成交量），与 v1 modules/visualizer_kline.py 同口径。
 * 累计成交量为 0 → 该点 null（不拿收盘价冒充均价）。
 *
 * ⚠️ 诚实红线（2026-11-12 修复）：amount 与 volume 必须**成对有效**才累加。
 * 旧实现分别判空、分别累加，单点缺失时会「分子没加、分母照加」（或反之），
 * 算出被稀释 / 放大的错误均价，且该缺失点仍输出一个看似精确的数字 —— 属用
 * 不完整数据编造。现改为：任一缺失 → 该点显 null（断线），且两者都不累加，
 * 保证后续累计的分子分母始终配对。
 */
export function intradayAvg(points: IntradayPoint[]): (number | null)[] {
  const out: (number | null)[] = []
  let cumAmount = 0
  let cumVolume = 0
  for (const p of points) {
    if (p.amount === null || p.volume === null) {
      out.push(null)
      continue
    }
    cumAmount += p.amount
    cumVolume += p.volume
    out.push(cumVolume > 0 && cumAmount > 0 ? cumAmount / cumVolume : null)
  }
  return out
}
