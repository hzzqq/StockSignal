import { z } from 'zod'
import {
  BreadthDivergenceSchema,
  type BreadthDivergence,
} from '@/api/schemas/breadthDivergence'
import {
  TemperatureBacktestSchema,
  type TemperatureBacktest,
} from '@/api/schemas/temperatureBacktest'
import {
  UserDashboardDataSchema,
  ReviewNotesDataSchema,
  type UserDashboardData,
  type ReviewNotesData,
} from '@/api/schemas/batchBWrite'

/**
 * parity B 批次 MSW 夹具。数值为演示值，字段形状逐字段对齐后端契约；
 * 时间戳固定常量（禁止 new Date() 冒充数据日）。
 *
 * 诚实空态变体：
 *  - 广度分化：含 red_ratio=null / ld_p90=null / current=null / z 单元格 null / 缺失月份；
 *  - 温度回测：含 available:false 且只有 reason 的降级变体（不补任何零值字段）。
 */

const FULL_YEARS = [2024, 2025, 2026]
const FULL_MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

export const breadthDivergenceFixture: BreadthDivergence = {
  available: true,
  calendar: {
    available: true,
    years: FULL_YEARS,
    months: FULL_MONTHS,
    z: [
      [0.3, 0.5, -0.2, 0.1, 0.8, -0.4, 0.6, 0.2, -0.1, 0.4, 0.7, 0.5],
      [-0.5, 0.2, 0.9, 0.3, -0.7, 0.1, 0.4, 0.6, 0.8, -0.3, 0.2, 0.1],
      [0.1, -0.2, 0.4, 0.7, 0.3, -0.6, 0.5, 0.2, -0.4, 0.8, 0.6, 0.3],
    ],
    latest_year: 2026,
  },
  divergence: {
    available: true,
    threshold_red: 50,
    ld_p90: 42,
    episodes: [
      {
        date: '2025-04-07',
        red_ratio: 0.12,
        limit_down: 320,
        limit_down_ratio: 0.08,
        zt_prev_ret: -3.2,
      },
      {
        date: '2025-07-18',
        red_ratio: 0.18,
        limit_down: 210,
        limit_down_ratio: 0.05,
        zt_prev_ret: -2.1,
      },
    ],
    current: {
      date: '2026-01-15',
      red_ratio: 0.31,
      limit_down: 45,
      limit_down_ratio: 0.01,
      is_divergent: false,
    },
    n_episodes: 2,
  },
  trend: {
    available: true,
    dates: ['2026-01-13', '2026-01-14', '2026-01-15'],
    red_ratio: [0.42, 0.28, 0.31],
    limit_down: [12, 28, 45],
  },
}

/** 缺失月份 / null 变体：锁定契约接受 honest 空态，不补零。 */
export const breadthDivergenceNullFixture: BreadthDivergence = {
  available: true,
  calendar: {
    available: true,
    years: [2026],
    months: [1], // 缺失其余月份
    z: [[null]], // 无数据单元格为 null
    latest_year: 2026,
  },
  divergence: {
    available: true,
    threshold_red: 50,
    ld_p90: null, // 样本不足，诚实为 null
    episodes: [
      {
        date: '2026-01-15',
        red_ratio: null,
        limit_down: null,
        limit_down_ratio: null,
        zt_prev_ret: null,
      },
    ],
    current: null, // 当前非事件日
    n_episodes: 1,
  },
  trend: {
    available: true,
    dates: ['2026-01-15'],
    red_ratio: [null],
    limit_down: [null],
  },
}

export const temperatureBacktestFullFixture: TemperatureBacktest = {
  available: true,
  data: { rows: 750, start: '2023-01-01', end: '2026-01-15' },
  baseline: {
    n: 750,
    next_mean_delta: 0.12,
    next_impr_rate: 0.55,
    d5_mean_delta: 0.31,
    d5_impr_rate: 0.58,
  },
  bands: [
    {
      level: 1,
      label: '极冷',
      color: '#3b82f6',
      n: 120,
      available: true,
      next_mean_delta: 0.22,
      next_impr_rate: 0.63,
      d5_mean_delta: 0.44,
      d5_impr_rate: 0.66,
      avg_next_red: 0.18,
      avg_d5_red: 0.21,
    },
    {
      level: 2,
      label: '偏冷',
      color: '#60a5fa',
      n: 200,
      available: true,
      next_mean_delta: 0.15,
      next_impr_rate: 0.58,
      d5_mean_delta: 0.33,
      d5_impr_rate: 0.6,
      avg_next_red: 0.24,
      avg_d5_red: 0.27,
    },
    {
      level: 3,
      label: '中性',
      color: '#9ca3af',
      n: 250,
      available: true,
      next_mean_delta: 0.08,
      next_impr_rate: 0.52,
      d5_mean_delta: 0.21,
      d5_impr_rate: 0.54,
      avg_next_red: 0.35,
      avg_d5_red: 0.37,
    },
    {
      level: 4,
      label: '偏热',
      color: '#f59e0b',
      n: 180,
      available: true,
      next_mean_delta: -0.04,
      next_impr_rate: 0.46,
      d5_mean_delta: -0.09,
      d5_impr_rate: 0.44,
      avg_next_red: 0.52,
      avg_d5_red: 0.49,
    },
    {
      level: 5,
      label: '极热',
      color: '#ef4444',
      n: 0,
      available: false, // 样本不足的带：不补任何统计字段
    },
  ],
  note: '演示回测结果，interval 取数不足的带如实标记 unavailable。',
}

/** 诚实降级：available:false 时只有 reason，其余字段全无。 */
export const temperatureBacktestDegradedFixture: TemperatureBacktest = {
  available: false,
  reason: '温度历史样本不足，无法进行回测（后端 honest 降级）',
}

/** 与 v2 页面真实组件 id 一致（snapshot/recommendation/breadth/event/backtest）。 */
export const userDashboardFixture: UserDashboardData = {
  widgets: ['snapshot', 'recommendation', 'breadth'],
}

export const reviewNotesFixture: ReviewNotesData = {
  date: '2026-01-15',
  content: '演示复盘笔记：今日广度分化未确认，等待次日确认信号。',
}

/**
 * 契约漂移守卫 A 段用（tests/unit/contract-drift.test.ts 由 team-lead 统一接线）。
 * 每个样本用对应 Zod schema 严格 parse，锁定 mock ↔ 契约自洽；
 * 含 null / 降级变体，防止「只给满数据」掩盖契约里的可空 / 可缺失字段。
 */
export const batchBFixturePairs: Array<{
  name: string
  schema: z.ZodTypeAny
  samples: unknown[]
}> = [
  {
    name: 'batch-b/breadth-divergence',
    schema: BreadthDivergenceSchema,
    samples: [breadthDivergenceFixture, breadthDivergenceNullFixture],
  },
  {
    name: 'batch-b/temperature-backtest',
    schema: TemperatureBacktestSchema,
    samples: [temperatureBacktestFullFixture, temperatureBacktestDegradedFixture],
  },
  {
    name: 'batch-b/user-dashboard-write',
    schema: UserDashboardDataSchema,
    samples: [userDashboardFixture],
  },
  {
    name: 'batch-b/review-notes-write',
    schema: ReviewNotesDataSchema,
    samples: [reviewNotesFixture],
  },
]
