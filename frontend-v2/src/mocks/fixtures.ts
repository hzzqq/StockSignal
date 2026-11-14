/**
 * 开发用 Mock 数据（演示性质，非真实行情）。
 * 结构严格对齐本仓真实数据文件（data/daily_snapshot.json、snapshot_*.json、
 * p1_signals/signal_*.json、paper_*.json、webapps 下各 meta.json），仅数值为示例，
 * 用于前端联调与组件测试。生产构建不加载本文件。
 */

export const dailySnapshot = {
  date: '2026-11-06',
  as_of: '2026-11-06',
  data_age_days: 0,
  generated_at: '2026-11-06T15:31:42',
  temperature: 33,
  cycle: '修复试探',
  score: 47.9,
  bias: '中性',
  confidence: 50,
  promo_overall: 6.3,
  ladder: { distribution: [[5, 2], [4, 2], [3, 3], [2, 4], [1, 21]], max_boards: 5, total_connect: 11 },
  position: {
    pct: 29,
    band: '偏空',
    color: '#00d486',
    reasons: [
      '市场温度 33 作为基准仓位',
      '次日方向「中性」加仓 0%',
      '梯队断档（晋级率<20%）：减仓 6%',
      '事件驱动因子不可用：不额外加减',
    ],
  },
  event_factor: { available: false, long_count: 0, adj: 0, as_of: '2026-10-21' },
  data_freshness: {
    status: 'stale',
    max_lag_days: 16,
    sources: {
      牧羊人情绪: { as_of: '2026-11-06', lag_days: 0, status: 'ok' },
      事件因子: { as_of: '2026-10-21', lag_days: 16, status: 'stale' },
      连板晋级率: { as_of: '2026-11-06', lag_days: 0, status: 'ok' },
      市场温度缓存: { as_of: '2026-11-04', lag_days: 2, status: 'warn' },
    },
  },
  indicators: {
    up_count: 2103,
    down_count: 2890,
    limit_up: 52,
    limit_down: 8,
    red_ratio: 0.42,
    median_chg: -0.31,
    turnover_amt: 18642.5,
    hb_wave10: 2.1,
    connect_hl: 5,
    connect_2b: 11,
    zt_fail_count: 14,
    fc_ratio: 0.79,
  },
  signals: [],
  scenario: [
    { name: '震荡偏弱', prob: 45, color: '#00d486', desc: '量能不足，板块轮动快', trigger: '成交<1.8万亿' },
    { name: '修复反弹', prob: 35, color: '#ff4d4f', desc: '超跌修复', trigger: '连板高度回升' },
    { name: '破位下行', prob: 20, color: '#9aa0b5', desc: '外部风险传导', trigger: '汇率异动' },
  ],
}

// 日期清单刻意含一个「无归档文件」的 2026-11-06，用于验证前端对该日期诚实报 not_found，
// 不回退今日快照冒充历史回放（真后端 data/snapshots/ 同理）。
export const snapshotDates = ['2026-11-06', '2026-09-21', '2026-09-20']

export const snapshots: Record<string, unknown> = {
  '2026-09-21': {
    ...dailySnapshot,
    date: '2026-09-21',
    data_age_days: 46,
    temperature: 41,
    cycle: '震荡上行',
    score: 55.2,
    position: { pct: 45, band: '中性', color: '#ff4d4f', reasons: ['市场温度 41 基准', '梯队健康加仓'] },
    data_freshness: { status: 'stale', max_lag_days: 46, sources: {} },
  },
  '2026-09-20': {
    ...dailySnapshot,
    date: '2026-09-20',
    data_age_days: 47,
    temperature: 39,
    score: 52.8,
    position: { pct: 40, band: '中性', color: '#ff4d4f', reasons: ['基准仓位'] },
  },
}

export const p1Signals: Record<string, unknown> = {
  'signal_fusion_h10.json': {
    generated_at: '2026-11-05T02:02:29',
    latest_date: '2026-10-21',
    top_long: [
      { symbol: 'sh688048', pred: 0.0479, rank: 1 },
      { symbol: 'sh688668', pred: 0.0447, rank: 0.999 },
      { symbol: 'sz300475', pred: 0.0423, rank: 0.998 },
    ],
    top_short: [
      { symbol: 'sz002594', pred: -0.0312, rank: 1 },
      { symbol: 'sh601012', pred: -0.0288, rank: 0.997 },
    ],
    model: { name: 'fusion_h10', horizon: 10 },
  },
  'signal_gru_h10.json': {
    generated_at: '2026-11-04T22:11:03',
    latest_date: '2026-10-21',
    top_long: [
      { symbol: 'sh600519', pred: 0.0391, rank: 1 },
      { symbol: 'sz000858', pred: 0.0355, rank: 0.992 },
    ],
    top_short: [{ symbol: 'sz300750', pred: -0.0291, rank: 1 }],
    model: { name: 'gru_h10', horizon: 10 },
  },
}

export const recommendation = {
  status: 'unavailable',
  reason: '股票池为空（演示 Mock：数据源不可用）',
  generated_at: '2026-11-05T19:24:04',
  disclaimer:
    '推荐由多算法融合筛选生成，附历史模拟统计，不构成投资建议；方向预测≈随机（4092 交易日回测结论），价值在筛选漏斗+风控方案+成本感知，请独立决策。',
}

export const virtualSim = {
  meta: { n_users: 10000, seed: 20261011, universe_size: 300, pool_valid: 286, start: '2024-01-01', end: '2026-09-30' },
  aggregate: { win_rate: 0.51, mean_return: 0.003 },
  profiles: [],
}

export const paperTrades: Record<string, unknown> = {
  admin: {
    init_cash: 1000000,
    cash: 870944,
    positions: { '600519': { name: '贵州茅台', qty: 100, avg_cost: 1290.56 } },
    trades: [
      { time: '2026-09-09 12:10', code: '600519', name: '贵州茅台', side: '买', price: 1290.56, qty: 100, amount: 129056 },
      { time: '2026-09-12 14:30', code: '300750', name: '宁德时代', side: '卖', price: 221.3, qty: 50, amount: 11065 },
    ],
    equity: [
      ['2026-09-09 12:10', 1000000],
      ['2026-09-12 14:30', 989935],
    ],
  },
}

export const webapps = [
  { dir: '3d-kline-city', title: '3D K线城', desc: '纯 Canvas 的 A 股 K 线城市：每根 K 线是一座建筑，高度编码涨跌、红涨绿跌。', entry: 'index.html', version: '1.0.0', added: '2026-11-02' },
  { dir: 'emotion-cycle-clock', title: '情绪周期钟', desc: '把市场情绪周期映射成时钟刻度，直观看当前所处阶段。', entry: 'index.html', version: '1.2.0', added: '2026-11-03' },
  { dir: 'thesis-showcase', title: '毕设展示台', desc: 'StockSignal 毕设成果交互展示页。', entry: 'index.html', version: '0.9.0', added: '2026-11-04' },
]

// W3 广度时序（聚合 snapshots 的 Mock；演示数值非真实行情）
export const breadthTimeseries = [
  { date: '2026-11-06', temperature: 33, up_count: 716, down_count: 4431, limit_up: 32, limit_down: 15, red_ratio: 13.9, median_chg: -1.92 },
  { date: '2026-11-05', temperature: 35, up_count: 2103, down_count: 2890, limit_up: 52, limit_down: 8, red_ratio: 42.0, median_chg: -0.31 },
  { date: '2026-11-04', temperature: 41, up_count: 3500, down_count: 1500, limit_up: 70, limit_down: 5, red_ratio: 70.0, median_chg: 0.8 },
  { date: '2026-11-03', temperature: 38, up_count: 1800, down_count: 3300, limit_up: 40, limit_down: 12, red_ratio: 35.3, median_chg: -0.55 },
  { date: '2026-11-02', temperature: 30, up_count: 900, down_count: 4200, limit_up: 25, limit_down: 20, red_ratio: 17.6, median_chg: -1.4 },
]

// W3 连板梯队明细（shepherd_ladder_history 的 Mock；演示数值非真实行情）
export const ladderDetail = [
  { date: '2026-11-06', distribution: { '5': 2, '4': 2, '3': 3, '2': 4, '1': 21 }, max_boards: 5, total_connect: 11, updated_at: '2026-11-06T15:31', suspect: false },
  { date: '2026-11-05', distribution: { '6': 1, '4': 2, '3': 5, '2': 9, '1': 65 }, max_boards: 6, total_connect: 18, updated_at: '2026-11-05T15:30', suspect: false },
  { date: '2026-11-04', distribution: { '7': 1, '5': 2, '4': 3, '3': 6, '2': 8, '1': 60 }, max_boards: 7, total_connect: 20, updated_at: '2026-11-04T15:31', suspect: false },
]

// W3 长周期广度历史（shepherd_history 的 Mock；演示数值非真实行情，个别字段为 NaN 后端已清洗）
export const breadthHistory = [
  { date: '2026-11-06', up_count: 2103, down_count: 2890, flat_count: 7, limit_up: 52, limit_down: 8, red_ratio: 42.0, connect_hl: 5, zt_fail_ratio: 12.3, zt_prev_ret: -0.8 },
  { date: '2026-11-05', up_count: 1800, down_count: 3300, flat_count: 12, limit_up: 40, limit_down: 12, red_ratio: 35.3, connect_hl: 4, zt_fail_ratio: 15.1, zt_prev_ret: 1.2 },
  { date: '2026-08-31', up_count: 3500, down_count: 1500, flat_count: 9, limit_up: 70, limit_down: 5, red_ratio: 70.0, connect_hl: 7, zt_fail_ratio: 9.0, zt_prev_ret: 2.3 },
]

// W3 后续簇 · 5 个真实数据源的 Mock（字段名与 2026-11-07 真扫一致，数值为演示、非真实行情）
// 注：p1SyncStatus 刻意**不含** target_dir，与后端 /p1-sync-status 的递归脱敏行为保持一致。
export const eventPool = {
  date: '2026-11-06',
  model: 'ev',
  source: 'P1-QuantFactor EV 事件因子',
  note: '统计意义上的超额收益概率排序，非买卖指令',
  count: 4,
  pool: [
    { rank: 1, symbol: 'sh600707', score: 100.0, raw_rank: 1.0, raw_pred: 0.098, signal: '看多', source: 'P1-ev-top_long' },
    { rank: 2, symbol: 'sh688048', score: 99.9, raw_rank: 0.999, raw_pred: 0.091, signal: '看多', source: 'P1-ev-top_long' },
    { rank: 3, symbol: 'sz300475', score: 98.7, raw_rank: 0.987, raw_pred: 0.084, signal: '看多', source: 'P1-ev-top_long' },
    { rank: 4, symbol: 'sh601088', score: 96.2, raw_rank: 0.962, raw_pred: 0.072, signal: '看多', source: 'P1-ev-top_long' },
  ],
}

export const predictionLog = [
  { date: '2026-11-02', temp: 30.2, cycle: '冰点', bias: '偏多', pct: 25, realized: 0.81, hit: true },
  { date: '2026-11-03', temp: 31.5, cycle: '退潮', bias: '偏空', pct: 15, realized: -0.42, hit: true },
  { date: '2026-11-04', temp: 34.0, cycle: '修复试探', bias: '中性', pct: 20, realized: 0.18, hit: false },
  { date: '2026-11-05', temp: 33.8, cycle: '修复试探', bias: '偏空', pct: 12, event_adj: 1, event_available: true, realized: null, hit: null },
  { date: '2026-11-06', temp: 33.0, cycle: '修复试探', bias: '中性', pct: 29, event_adj: 2, event_available: true, realized: null, hit: null },
]

export const p1SyncStatus = {
  run_at: '2026-11-07T15:19:07',
  mode: 'scheduler',
  interval_minutes: 60,
  dry_run: false,
  ok: true,
  written: [],
  skipped: [
    'baseline: 内容一致（md5 相同），跳过',
    'ens: 内容一致（md5 相同），跳过',
    'rotation: 全部候选结构无效（拒绝写入）',
  ],
  errors: [],
  all_invalid: false,
  counts: { copy: 0, unchanged: 5, target_newer: 0, skip: 1 },
  health: {
    status: 'warn',
    message: '4 个副本超出新鲜度 SLA',
    latest: '2026-10-21',
    age_days: 17,
    models: ['baseline', 'ens', 'ev', 'fusion', 'gru'],
    rows: [
      { file: 'signal_ev_h10.json', model_key: 'ev', latest_date: '2026-10-21', age_days: 17, structural_ok: true, freshness_ok: false, errors: ['数据滞后'] },
      { file: 'signal_gru_h10.json', model_key: 'gru', latest_date: '2026-10-21', age_days: 17, structural_ok: true, freshness_ok: false, errors: ['数据滞后'] },
    ],
  },
  prev_run_at: '2026-11-07T14:19:05',
}

// ⚠️ 演示数据含负收益/负 Sharpe，如实保留，不取绝对值、不包装成「策略领先」。
export const backtestRuns = {
  runs: [
    {
      run_id: '20261023-162048-009d8c07562a',
      created_at: '2026-10-23T16:20:48',
      status: 'success',
      params: { ticker: '601088', start: '2025-10-23', end: '2026-10-23', strategy: 'multi_factor', initial_capital: 100000 },
      summary: { ticker: '601088', strategy: 'multi_factor', initial_capital: 100000, final_value: 98116.08, total_return_pct: -1.88, max_drawdown_pct: -18.81, sharpe_ratio: 0.02, win_rate_pct: 52.17, profit_factor: 1.05, avg_trade_return_pct: 0.12, trade_count: 23, start_date: '2025-10-23', end_date: '2026-10-23' },
    },
    {
      run_id: '20261024-093012-3b21f0c8a441',
      created_at: '2026-10-24T09:30:12',
      status: 'success',
      params: { ticker: '600519', start: '2025-10-24', end: '2026-10-24', strategy: 'mean_reversion', initial_capital: 100000 },
      summary: { ticker: '600519', strategy: 'mean_reversion', initial_capital: 100000, final_value: 104230.5, total_return_pct: 4.23, max_drawdown_pct: -9.12, sharpe_ratio: 0.41, win_rate_pct: 55.1, profit_factor: 1.18, avg_trade_return_pct: 0.21, trade_count: 31, start_date: '2025-10-24', end_date: '2026-10-24' },
    },
    {
      run_id: '20261025-141705-77e0a9d21b03',
      created_at: '2026-10-25T14:17:05',
      status: 'success',
      params: { ticker: '300750', start: '2025-10-25', end: '2026-10-25', strategy: 'momentum', initial_capital: 100000 },
      summary: { ticker: '300750', strategy: 'momentum', initial_capital: 100000, final_value: 95340.0, total_return_pct: -4.66, max_drawdown_pct: -21.4, sharpe_ratio: -0.31, win_rate_pct: 47.8, profit_factor: 0.89, avg_trade_return_pct: -0.15, trade_count: 27, start_date: '2025-10-25', end_date: '2026-10-25' },
    },
  ],
}

export const dataRefreshState = {
  attempts_today: 1,
  last_run_date: '2026-11-05',
  last_result: 'ok',
  finished_at: '2026-11-05T19:23:31',
  last_csv_date: '2026-11-02',
  detail: 'exit=0 killed=False since=2026-10-19 末行 2026-11-02 → 2026-11-05（推进）',
}

// ── 因子分析（factor-analysis）Mock：演示数值，非真实行情 ──
// 结构严格对齐 backend/api/read_routes.py factor_analysis() 的 data 字典
// （ic_series / ic_summary / layered_cum / long_short_cum / errs / date / note）。
// 数值为确定性静态样例（非实时），与后端离线降级口径一致：缺失即 null、不补 0。
const factorDates = (() => {
  const out: string[] = []
  let d = new Date('2026-09-21T00:00:00Z')
  for (let i = 0; i < 30; i++) {
    out.push(d.toISOString().slice(0, 10))
    d = new Date(d.getTime() + 86_400_000)
  }
  return out
})()

const factorIcSeries = factorDates.map((date, i) => ({
  date,
  ic: Number((0.03 + 0.05 * Math.sin(i / 3) - 0.02 * (i % 5)).toFixed(4)),
}))

// 分层累计：layer 0 = 最高因子组（累计最高），layer 4 = 最低因子组（累计最低）。
const factorLayerCum = factorDates.map((date, i) => {
  const rec: Record<string, unknown> = { date }
  for (let layer = 0; layer < 5; layer++) {
    const daily = 0.004 - layer * 0.002
    rec[String(layer)] = Number((Math.pow(1 + daily, i + 1) - 1).toFixed(4))
  }
  return rec
})

const factorLsCum = factorDates.map((date, i) => ({
  date,
  ic: Number((Math.pow(1 + 0.006, i + 1) - 1).toFixed(4)),
}))

export const factorAnalysis = {
  codes: ['600519', '000001', '300750'],
  days: 250,
  factor: 'momentum',
  forward: 1,
  n_layers: 5,
  ic_series: factorIcSeries,
  ic_summary: {
    n: 30,
    ic_mean: Number((0.0265).toFixed(4)),
    ic_std: Number((0.0589).toFixed(4)),
    ir: Number((0.0265 / 0.0589).toFixed(3)),
    positive_ratio: 0.63,
    t_stat: Number((0.0265 / (0.0589 / Math.sqrt(30))).toFixed(2)),
  },
  layered_cum: factorLayerCum,
  long_short_cum: factorLsCum,
  errs: [],
  date: factorDates[factorDates.length - 1],
  note: '逐标的独立取数、独立降级；缺失为 null 且不补 0；有效标的<3 不给出因子结论（与 modules.factor_analysis.build_panels 诚实红线一致）。',
}

// ───────── 事件因子回测（event-backtest）Mock，字段名与后端 modules.event_backtest.run 契约一致。
// 演示数值对应「极端恐慌（跌停占比前 10%）→ 次日红盘」的已验证信号（sentiment_edge）；
// 非实时行情，仅用于契约守卫与组件测试。z=null 的诚实空态见 eventBacktestSmallSample。
export const eventBacktest = {
  available: true,
  metric: 'limit_down_ratio',
  tail: 0.1,
  direction: 'high',
  horizon: 1,
  n_event: 296,
  n_base: 3800,
  base_rate: 0.498,
  event_rate: 0.625,
  edge_pp: 12.7,
  z: 4.36,
  distribution: [
    { bucket: '0.0–0.1', event_count: 1, base_count: 120 },
    { bucket: '0.1–0.2', event_count: 2, base_count: 210 },
    { bucket: '0.2–0.3', event_count: 5, base_count: 340 },
    { bucket: '0.3–0.4', event_count: 10, base_count: 520 },
    { bucket: '0.4–0.5', event_count: 18, base_count: 610 },
    { bucket: '0.5–0.6', event_count: 42, base_count: 700 },
    { bucket: '0.6–0.7', event_count: 65, base_count: 640 },
    { bucket: '0.7–0.8', event_count: 78, base_count: 410 },
    { bucket: '0.8–0.9', event_count: 48, base_count: 180 },
    { bucket: '0.9–1.0', event_count: 27, base_count: 70 },
  ],
  example_dates: [
    { date: '2015-06-26', metric_value: 8.92, forward_red_day_frac: 0.0 },
    { date: '2015-07-08', metric_value: 9.41, forward_red_day_frac: 1.0 },
    { date: '2018-02-09', metric_value: 7.6, forward_red_day_frac: 1.0 },
    { date: '2020-02-03', metric_value: 8.1, forward_red_day_frac: 1.0 },
    { date: '2024-01-31', metric_value: 6.3, forward_red_day_frac: 1.0 },
    { date: '2015-08-25', metric_value: 7.2, forward_red_day_frac: 0.0 },
    { date: '2016-01-07', metric_value: 6.9, forward_red_day_frac: 1.0 },
    { date: '2019-05-09', metric_value: 5.8, forward_red_day_frac: 0.0 },
    { date: '2022-03-15', metric_value: 5.1, forward_red_day_frac: 1.0 },
    { date: '2023-08-22', metric_value: 4.7, forward_red_day_frac: 1.0 },
  ],
  method: 'two-proportion z-test（pooled）on forward red-day binary observations',
  honesty_notes: [
    '方法：walk-forward（第 i 天阈值只用 [0,i) 历史分位，无未来函数）。',
    '结果度量：前向 N 日「红盘日占比」（up_count>down_count），非指数收益率。',
    '指标均为尺度无关的占比类（跨年代采样规模可比）。',
  ],
}

// 小样本诚实空态：触发观测不足 MIN_N=30 → z=null，仅描述性参考（前端不报显著性）。
export const eventBacktestSmallSample = {
  ...eventBacktest,
  n_event: 12,
  n_base: 3800,
  base_rate: 0.498,
  event_rate: 0.583,
  edge_pp: 8.5,
  z: null,
  honesty_notes: [
    ...eventBacktest.honesty_notes,
    '触发观测 12 < 30，显著性（z）未计算，仅作描述性参考。',
  ],
}

// W4 后续簇 · 策略回测（backtest）Mock，字段名与后端 /api/v2/read/backtest 契约一致。
// 数值为确定性静态样例（非实时），与 modules.backtest.BacktestResult 口径一致：null 即缺失、不补 0。
const backtestDates = (() => {
  const out: string[] = []
  let d = new Date('2024-01-02T00:00:00Z')
  for (let i = 0; i < 30; i++) {
    // 跳过周末，贴近真实交易日序列
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) {
      out.push(d.toISOString().slice(0, 10))
    }
    d = new Date(d.getTime() + 86_400_000)
  }
  return out.slice(0, 30)
})()

const backtestEquity = (() => {
  let cum = 0
  let peak = 0
  return backtestDates.map((date, i) => {
    const daily = 0.0015 + 0.004 * Math.sin(i / 4) - 0.002 * (i % 6)
    cum += daily * 100
    const dd = cum - Math.max(peak, cum)
    peak = Math.max(peak, cum)
    return {
      date,
      cumulative_return: Number(cum.toFixed(2)),
      total_asset: Number((100000 * (1 + cum / 100)).toFixed(2)),
      drawdown: Number((dd < 0 ? dd : 0).toFixed(2)),
    }
  })
})()

export const backtest = {
  ticker: '600519',
  strategy: 'multi_factor',
  start: '2024-01-01',
  end: '2024-12-31',
  initial_capital: 100000,
  final_value: Number((100000 * (1 + backtestEquity[backtestEquity.length - 1].cumulative_return / 100)).toFixed(2)),
  total_return_pct: backtestEquity[backtestEquity.length - 1].cumulative_return,
  annualized_return_pct: Number((6.2).toFixed(2)),
  max_drawdown_pct: Number((Math.min(...backtestEquity.map((r) => r.drawdown))).toFixed(2)),
  sharpe_ratio: Number((1.84).toFixed(2)),
  win_rate_pct: Number((58.33).toFixed(2)),
  profit_factor: Number((2.15).toFixed(2)),
  avg_trade_return_pct: Number((2.41).toFixed(2)),
  trade_count: 12,
  exposure_pct: Number((73.5).toFixed(2)),
  start_date: backtestDates[0],
  end_date: backtestDates[backtestDates.length - 1],
  equity_curve: backtestEquity,
  trades: [
    { entry_date: backtestDates[0], exit_date: backtestDates[4], entry_price: 1685.0, exit_price: 1712.5, profit_pct: 1.63, exit_reason: '止盈', bars_held: 4 },
    { entry_date: backtestDates[6], exit_date: backtestDates[9], entry_price: 1702.0, exit_price: 1668.4, profit_pct: -1.98, exit_reason: '止损', bars_held: 3 },
    { entry_date: backtestDates[12], exit_date: backtestDates[18], entry_price: 1690.0, exit_price: 1745.2, profit_pct: 3.27, exit_reason: '最大持仓期', bars_held: 6 },
    { entry_date: backtestDates[20], exit_date: backtestDates[24], entry_price: 1730.0, exit_price: 1758.9, profit_pct: 1.67, exit_reason: '策略卖出', bars_held: 4 },
    { entry_date: backtestDates[26], exit_date: backtestDates[29], entry_price: 1745.0, exit_price: 1760.1, profit_pct: 0.86, exit_reason: '最大持仓期', bars_held: 3 },
  ],
  date: backtestDates[backtestDates.length - 1],
  note: '单标的独立回测；取数为空时诚实返回 insufficient_data 而非补零曲线；total_return/sharpe/win_rate 等口径与 modules.backtest.Backtester 一致。',
}

// W4 后续簇 · 市场全景 / 状态机（market-panorama）Mock，字段名与后端契约一致。
// 数值为确定性静态样例（非实时），与 modules.market_regime / modules.shepherd_history 口径一致：
// null = 字段缺失、不补 0；regime 与 shepherd 同页共享（56/57 两页复用）。
const mpDates = (() => {
  const out: string[] = []
  let d = new Date('2026-08-01T00:00:00Z')
  for (let i = 0; i < 20; i++) {
    out.push(d.toISOString().slice(0, 10))
    d = new Date(d.getTime() + 86_400_000)
  }
  return out
})()

export const marketPanorama = {
  k: 8,
  regime: {
    available: true,
    data: { rows: 4771, start: '2007-01-04', end: '2026-08-21' },
    latest: {
      date: mpDates[mpDates.length - 1],
      state: '震荡',
      confidence: 0.42,
      metrics: { red_ratio: 51.3, limit_up: 40, limit_down: 8 },
    },
    state_distribution: { 普涨: 612, 结构牛: 488, 震荡: 2210, 恐慌: 905, 暴跌: 556 },
    transition_matrix: {
      普涨: { 普涨: 0.2, 结构牛: 0.2, 震荡: 0.2, 恐慌: 0.2, 暴跌: 0.2 },
      结构牛: { 普涨: 0.2, 结构牛: 0.2, 震荡: 0.2, 恐慌: 0.2, 暴跌: 0.2 },
      震荡: { 普涨: 0.2, 结构牛: 0.2, 震荡: 0.2, 恐慌: 0.2, 暴跌: 0.2 },
      恐慌: { 普涨: 0.2, 结构牛: 0.2, 震荡: 0.2, 恐慌: 0.2, 暴跌: 0.2 },
      暴跌: { 普涨: 0.2, 结构牛: 0.2, 震荡: 0.2, 恐慌: 0.2, 暴跌: 0.2 },
    },
    analogs: [
      { date: '2023-05-04', distance: 1.2, state: '普涨', metrics: { red_ratio: 62.0, limit_up: 55, limit_down: 3 },
        forward: { d5: { avg_red: 55.0, up_frac: 0.6, median_delta: 1.1 } } },
      { date: '2021-09-15', distance: 1.8, state: '震荡', metrics: { red_ratio: 49.0, limit_up: 30, limit_down: 12 },
        forward: { d5: { avg_red: 50.5, up_frac: 0.52, median_delta: -0.4 } } },
    ],
  },
  shepherd_latest: {
    date: mpDates[mpDates.length - 1],
    red_ratio: 51.3,
    limit_up: 40,
    limit_down: 8,
    connect_hl: 6,
    zt_fail_ratio: 0.19,
  },
  shepherd_series: mpDates.map((date, i) => ({
    date,
    red_ratio: Number((48 + 6 * Math.sin(i / 3)).toFixed(1)),
    limit_up: 30 + (i % 20),
    limit_down: 8 + (i % 10),
    connect_hl: 4 + (i % 5),
    zt_fail_ratio: Number((0.2 - 0.01 * (i % 8)).toFixed(2)),
  })),
  shepherd_unavailable: [['zt_fail_ratio', '该日数据源缺失']],
  date: mpDates[mpDates.length - 1],
  note: '市场状态五档=规则可解释分类（modules.market_regime，阈值由全样本分位定）；广度真值=本地历史快照（data/shepherd_history.json，离线零网）；历史相似 ≠ 预测。',
}

// Tier1 · 持仓中心（portfolio）Mock，字段名与后端 /api/v2/read/portfolio 契约一致。
// 数值为确定性静态样例（非实时）：本地模拟持仓 + FIFO 盈亏 + 收益归因 + 尽力而为净值曲线。
// ⚠️ 缺失值与曲线不可用如实保留，禁止补 0 / 禁止用当前日期兜底。
const pfDates = (() => {
  const out: string[] = []
  const d = new Date('2026-01-01T00:00:00Z')
  for (let i = 0; i < 24; i++) {
    const x = new Date(d)
    x.setUTCDate(d.getUTCDate() + i)
    out.push(x.toISOString().slice(0, 10))
  }
  return out
})()

export const portfolio = {
  summary: {
    total_cost: 212000,
    total_market_value: 220500,
    total_pnl: 8500,
    total_pnl_pct: 4.01,
    position_count: 3,
  },
  positions: [
    { ticker: '600519', name: '贵州茅台', buy_date: '2026-01-02', buy_price: 1700, shares: 100, remaining_shares: 100, cost: 170000, current_price: 1800, market_value: 180000, realized_pnl: 0, pnl: 10000, pnl_pct: 5.88 },
    { ticker: '000001', name: '平安银行', buy_date: '2026-01-03', buy_price: 12, shares: 1000, remaining_shares: 500, cost: 6000, current_price: 11, market_value: 5500, realized_pnl: 0, pnl: -500, pnl_pct: -8.33 },
    { ticker: '300750', name: '宁德时代', buy_date: '2026-01-04', buy_price: 180, shares: 200, remaining_shares: 200, cost: 36000, current_price: 175, market_value: 35000, realized_pnl: 0, pnl: -1000, pnl_pct: -2.78 },
  ],
  attribution: [
    { ticker: '600519', name: '贵州茅台', pnl: 10000, pnl_pct: 5.88, contribution: 117.65 },
    { ticker: '000001', name: '平安银行', pnl: -500, pnl_pct: -8.33, contribution: -5.88 },
    { ticker: '300750', name: '宁德时代', pnl: -1000, pnl_pct: -2.78, contribution: -11.76 },
  ],
  weights: [
    { ticker: '600519', name: '贵州茅台', weight_pct: 81.63 },
    { ticker: '000001', name: '平安银行', weight_pct: 2.49 },
    { ticker: '300750', name: '宁德时代', weight_pct: 15.87 },
  ],
  curve: pfDates.map((date, i) => ({
    date,
    portfolio: Number((100 + i * 0.4 + (i % 3)).toFixed(2)),
    benchmark: Number((100 + i * 0.25 - (i % 4)).toFixed(2)),
  })),
  curve_available: true,
  date: null,
  note: '持仓为本地模拟/历史数据（data/portfolio.csv），仅供学习不构成投资建议；现价为最近可得收盘（离线口径可能为静态样本）；净值曲线为尽力而为的历史还原，缺失则如实标注。',
}

// Tier1 · 资金流向（fund-flow）Mock，字段名与后端 /api/v2/read/fund-flow 契约一致。
// 四块各自独立 available；演示数值非实时行情，金额已折算为亿元。
export const fundFlow = {
  northbound: {
    available: true,
    trade_date: '2026-11-08',
    total_inflow: 5.0,
    sh_inflow: 3.0,
    sz_inflow: 2.0,
    northbound_net_available: true,
    boards: [
      { board: '沪股通', direction: '北向', trade_net: 12.0, net_inflow: 34.0, up_count: 300, down_count: 150, index_chg_pct: 1.2 },
      { board: '深股通', direction: '北向', trade_net: 8.0, net_inflow: 20.0, up_count: 280, down_count: 160, index_chg_pct: 0.9 },
    ],
    last_net_buy: 99.0,
    last_net_buy_date: '2024-08-15',
    cumulative: 18000.0,
    cumulative_date: '2024-08-15',
  },
  industry: {
    available: true,
    rows: [
      { industry: '半导体', chg_pct: 2.5, inflow: 500.0, outflow: 400.0, net: 100.0, leader: '中芯国际', leader_chg_pct: 5.1 },
      { industry: '电池', chg_pct: 1.8, inflow: 300.0, outflow: 260.0, net: 40.0, leader: '宁德时代', leader_chg_pct: 3.2 },
      { industry: '银行', chg_pct: -1.1, inflow: 200.0, outflow: 250.0, net: -50.0, leader: '招商银行', leader_chg_pct: -0.8 },
    ],
  },
  market: {
    available: true,
    rows: [
      { date: '2026-11-04', index_chg_pct: 0.8, main_net: 150.0, main_net_pct: 3.8, super_net: 80.0, big_net: 70.0, mid_net: -60.0 },
      { date: '2026-11-05', index_chg_pct: -0.2, main_net: -40.0, main_net_pct: -1.1, super_net: -20.0, big_net: -20.0, mid_net: 30.0 },
      { date: '2026-11-06', index_chg_pct: 0.5, main_net: 120.0, main_net_pct: 3.1, super_net: 60.0, big_net: 60.0, mid_net: -50.0 },
      { date: '2026-11-07', index_chg_pct: -0.3, main_net: -80.0, main_net_pct: -2.2, super_net: -40.0, big_net: -40.0, mid_net: 30.0 },
    ],
  },
  margin: {
    available: true,
    rows: [
      { date: '2026-11-03', sh_rzmr_yi: 290.0, sz_rzmr_yi: 190.0, total_rzmr_yi: 480.0, sh_rzye_yi: 6950.0, sz_rzye_yi: 5950.0, total_rzye_yi: 12900.0, sh000001: 3280.0, sz399001: 10950.0, sz399006: 2280.0 },
      { date: '2026-11-04', sh_rzmr_yi: 295.0, sz_rzmr_yi: 195.0, total_rzmr_yi: 490.0, sh_rzye_yi: 6970.0, sz_rzye_yi: 5980.0, total_rzye_yi: 12950.0, sh000001: 3300.0, sz399001: 11000.0, sz399006: 2300.0 },
      { date: '2026-11-05', sh_rzmr_yi: 298.0, sz_rzmr_yi: 198.0, total_rzmr_yi: 496.0, sh_rzye_yi: 6990.0, sz_rzye_yi: 6000.0, total_rzye_yi: 12990.0, sh000001: 3310.0, sz399001: 11020.0, sz399006: 2310.0 },
      { date: '2026-11-06', sh_rzmr_yi: 300.0, sz_rzmr_yi: 200.0, total_rzmr_yi: 500.0, sh_rzye_yi: 7000.0, sz_rzye_yi: 6000.0, total_rzye_yi: 13000.0, sh000001: 3300.0, sz399001: 11000.0, sz399006: 2300.0 },
    ],
    latest: { date: '2026-11-06', total_rzmr_yi: 500.0, total_rzye_yi: 13000.0, sh_rzmr_yi: 300.0, sz_rzmr_yi: 200.0, rzmr_change_yi: 12.5, rzye_change_yi: -8.3, rzmr_change_pct: 2.5, rzye_change_pct: -0.6 },
  },
  note: '资金流向数据来自东方财富/同花顺网络接口（fundflow / margin_trading 数据层），离线或接口受限时逐块诚实降级（该块显示「数据暂不可用」而非编造数值）。北向实时净买额自 2024-08-16 起停披露，模块以「最近一次真实披露」与「历史累计净买入」兜底；金额单位均为亿元，非实时、非投资建议。',
}

// Tier1 · 实盘交易只读概览（trading-account）Mock，字段名与后端 /api/v2/read/trading-account 契约一致。
// ⚠️ V2 此处只读：聚合本地模拟账本 data/paper_<user>.json；金额单位为「元」，非实时、非真实券商。
export const tradingAccount = {
  account: {
    broker_type: 'sim', mode: '模拟', init_cash: 1000000, cash: 870944,
    position_cost: 129056, total_assets: 1000000, available: true,
  },
  positions: [
    { code: '600519', name: '贵州茅台', qty: 100, avg_cost: 1290.56, cost_basis: 129056 },
    { code: '000001', name: '平安银行', qty: 500, avg_cost: 11.32, cost_basis: 5660 },
  ],
  orders: [
    { time: '2026-09-09 12:10', code: '600519', name: '贵州茅台', side: '买', price: 1290.56, qty: 100, amount: 129056 },
    { time: '2026-09-10 09:45', code: '000001', name: '平安银行', side: '买', price: 11.32, qty: 500, amount: 5660 },
  ],
  note: '本页为 V2 只读概览，读取本地模拟账本（data/paper_<user>.json），反映模拟撮合下的账户 / 持仓 / 订单流水，非真实券商实盘；实时下单与真实券商（QMT / 同花顺）写能力仅在 v1 实盘交易页 /api/trade/* 提供，V2 不暴露任何写接口。数据仅供参考，非投资建议。',
}

// Tier2 · 宏观数据（macro-data）Mock，字段名与后端 /api/v2/read/macro-data 契约一致。
// 各指标独立：取不到为 null（诚实降级，不补 0）；regime 为规则化评分或 null。数值为演示。
export const macroData = {
  indicators: {
    pmi: { key: 'pmi', name: '制造业 PMI', unit: '%', freq: '月', source: '国家统计局', region: '国内', desc: '荣枯线 50；>50 景气扩张', value: 51.2, prev: 50.8, change: 0.4, date: '2026-11-01', stale: false, from_cache: true },
    cpi: { key: 'cpi', name: 'CPI 同比', unit: '%', freq: '月', source: '国家统计局', region: '国内', desc: '通胀水平', value: 0.9, prev: 1.1, change: -0.2, date: '2026-10-01', stale: false, from_cache: true },
    m2: { key: 'm2', name: 'M2 同比', unit: '%', freq: '月', source: '央行', region: '国内', desc: '广义货币供应', value: 8.3, prev: 8.1, change: 0.2, date: '2026-10-01', stale: false, from_cache: true },
    lpr: { key: 'lpr', name: 'LPR（1 年期）', unit: '%', freq: '月', source: '央行', region: '国内', desc: '贷款市场报价利率', value: 3.1, prev: 3.1, change: 0.0, date: '2026-10-01', stale: false, from_cache: true },
    dxy: { key: 'dxy', name: '美元指数 DXY', unit: '点', freq: '日', source: 'ICE / 东方财富', region: '全球', desc: '美元强弱', value: 102.3, prev: 101.8, change: 0.5, date: '2026-11-08', stale: false, from_cache: true },
    us_treasury_10y: { key: 'us_treasury_10y', name: '美债 10Y 收益率', unit: '%', freq: '日', source: '美国财政部', region: '全球', desc: '全球资产定价锚', value: 4.1, prev: 4.2, change: -0.1, date: '2026-11-08', stale: false, from_cache: true },
    us_cpi: { key: 'us_cpi', name: '美国 CPI 同比', unit: '%', freq: '月', source: '美国劳工部', region: '全球', desc: '美国通胀', value: 2.8, prev: 3.0, change: -0.2, date: '2026-10-01', stale: false, from_cache: true },
    usd_cny: { key: 'usd_cny', name: '美元兑人民币(USD/CNY)', unit: '', freq: '日', source: '中国银行', region: '全球', desc: '人民币汇率', value: 7.12, prev: 7.15, change: -0.03, date: '2026-11-08', stale: false, from_cache: true },
    us_sp500: { key: 'us_sp500', name: '标普500指数', unit: '点', freq: '日', source: '东方财富', region: '全球', desc: '美股大盘基准', value: 5980.0, prev: 5950.0, change: 30.0, date: '2026-11-07', stale: false, from_cache: true },
    hsi: { key: 'hsi', name: '恒生指数', unit: '点', freq: '日', source: '东方财富', region: '全球', desc: '港股情绪', value: 19800.0, prev: 19600.0, change: 200.0, date: '2026-11-07', stale: false, from_cache: true },
    fed_funds_rate: { key: 'fed_funds_rate', name: '美联储联邦基金利率', unit: '%', freq: '议息', source: '美联储', region: '全球', desc: '联邦基金目标利率', value: 4.5, prev: 4.5, change: 0.0, date: '2026-09-01', stale: false, from_cache: true },
    // 取不到的指标：如实 null（演示诚实降级，不补 0）
    us_ism_pmi: null,
  },
  regime: {
    score: 58,
    sub: { dxy: 55.0, us_treasury_10y: 60.0, us_cpi: 64.0, usd_cny: 51.0 },
    parts: { dxy: 102.3, us_treasury_10y: 4.1, us_cpi: 2.8, usd_cny: 7.12 },
    yield_curve: 0.35,
    cn_us_spread: -0.1,
    dates: { dxy: '2026-11-08', us_treasury_10y: '2026-11-08', us_cpi: '2026-10-01', usd_cny: '2026-11-08' },
  },
  unavailable: ['us_ism_pmi'],
  note: '宏观数据来自国家统计局 / 央行 / 东方财富 / 新浪等公开源（macro_data：库优先 / 网络兜底），离线或接口受限时逐指标诚实降级（取不到显示「—」）。全球风险评分为规则化合成，非模型预测；非实时、非投资建议。',
}

// ───────── 龙虎榜（dragon-tiger / 85 页 V2 化）─────────
// 数值为演示、非真实行情；净买额单位亿元（net_yi）；detail 为原始明细行（列名随数据源版本变化）。
export const dragonTiger = {
  date: '20261109',
  count: 3,
  net_col: '净买额',
  net_sum_yi: 2.1,
  buy_top: [
    { code: '600519', name: '贵州茅台', net_yi: 2.5 },
    { code: '300750', name: '宁德时代', net_yi: 0.8 },
  ],
  sell_top: [{ code: '000001', name: '平安银行', net_yi: -1.2 }],
  detail: [
    { 代码: '600519', 名称: '贵州茅台', 净买额: 2.5e8 },
    { 代码: '000001', 名称: '平安银行', 净买额: -1.2e8 },
    { 代码: '300750', 名称: '宁德时代', 净买额: 0.8e8 },
  ],
  unavailable: [],
  note: '龙虎榜明细=东财接口（modules.lhb.fetch_lhb，30 分钟缓存，按交易日更新，非实时行情）；净买额口径以数据源列为准。',
}

// ───────── 题材热点（theme / 75 页 V2 化）─────────
// 数值为演示、非真实行情；concepts 含派生字段（chg/turnover_p/lifecycle/mv/leader）。
export const theme = {
  concepts: [
    { name: 'AI', chg: 3.5, turnover_p: 80, lifecycle: '高潮', mv: 1e12, turnover: 8, up: 10, down: 2, leader: '寒武纪' },
    { name: '机器人', chg: 1.2, turnover_p: 50, lifecycle: '发酵', mv: 8e11, turnover: 5, up: 8, down: 3, leader: '拓普集团' },
    { name: '光伏', chg: -2.1, turnover_p: 90, lifecycle: '退潮', mv: 5e11, turnover: 9, up: 3, down: 9, leader: '—' },
  ],
  summary: { count: 3, n_up: 2, n_down: 1, top_name: 'AI', top_chg: 3.5 },
  lifecycle_counts: { 高潮: 1, 发酵: 1, 退潮: 1 },
  unavailable: [],
  note: '题材来自东财概念板块快照（modules.theme_heat，120 秒缓存，非实时行情）；生命周期为启发式分类，非预测。',
}

export const themeTransmission = {
  status: 'ok',
  basis: '文本共现',
  disclaimer: '关联度高只说明消息在文本上更贴近它，不代表受益程度，更不是收益预测。',
  entries: [
    { name: '寒武纪', code: '688256', score: 9, direction: '利好', dir_color: '#dc2626', concepts: '算力', evidence: '算力需求超预期', direct: true },
  ],
  concepts_hit: ['算力'],
  members_unavailable: [],
  n_titles: 2,
  n_concepts: 1,
}

// 实时强势榜（strong）Mock：多因子评分（涨幅 0.40 + 量比 0.30 + 换手 0.20 + 成交额 0.10，启发式非预测）。
// score = 0.4*s_chg + 0.3*s_vr + 0.2*s_to + 0.1*s_amt（四项均为百分位 0-100）。以下数值为演示、非真实行情。
export const strong = {
  items: [
    { rank: 1, code: '688256', name: '寒武纪', price: 95.0, chg: 5.6, amount: 2e9, turnover: 8.0, vol_ratio: 2.1, score: 88.3, s_chg: 96.0, s_vr: 92.0, s_to: 90.0, s_amt: 70.0 },
    { rank: 2, code: '300750', name: '宁德时代', price: 210.0, chg: 2.1, amount: 4e9, turnover: 3.0, vol_ratio: 1.5, score: 71.4, s_chg: 80.0, s_vr: 70.0, s_to: 60.0, s_amt: 95.0 },
    { rank: 3, code: '600519', name: '贵州茅台', price: 1685.0, chg: 3.5, amount: 5e9, turnover: 1.5, vol_ratio: 1.2, score: 66.2, s_chg: 90.0, s_vr: 55.0, s_to: 40.0, s_amt: 99.0 },
    { rank: 4, code: '000001', name: '平安银行', price: 11.5, chg: -1.2, amount: 3e9, turnover: 2.5, vol_ratio: 0.9, score: 42.0, s_chg: 20.0, s_vr: 30.0, s_to: 45.0, s_amt: 80.0 },
    { rank: 5, code: '601318', name: '中国平安', price: 48.0, chg: 0.8, amount: 2.5e9, turnover: 1.8, vol_ratio: 1.1, score: 51.7, s_chg: 60.0, s_vr: 48.0, s_to: 38.0, s_amt: 78.0 },
    { rank: 6, code: '002594', name: '比亚迪', price: 260.0, chg: -2.4, amount: 3.5e9, turnover: 4.0, vol_ratio: 1.3, score: 38.5, s_chg: 10.0, s_vr: 40.0, s_to: 55.0, s_amt: 82.0 },
  ],
  src_label: '东财实时快照（直连）',
  kicked: [],
  unavailable: [],
  date: null,
}

// 板块轮动（sector-rotation）Mock：复用后端 get_industry_fund_flow 字段结构。
// 净额单位=亿元（与后端 _ff_yi 一致），null = 该行业净额取数缺失。
export const sectorRotation = {
  items: [
    { name: '半导体', chg_pct: 3.52, net: 18.6, leader: '中微公司', leader_chg_pct: 6.21 },
    { name: '白酒', chg_pct: -1.24, net: -5.3, leader: '贵州茅台', leader_chg_pct: -0.52 },
    { name: '银行', chg_pct: 0.81, net: 12.4, leader: '招商银行', leader_chg_pct: 1.12 },
    { name: '军工', chg_pct: 2.07, net: 7.8, leader: '中航沈飞', leader_chg_pct: 3.44 },
    { name: '新能源', chg_pct: 1.93, net: 9.1, leader: '宁德时代', leader_chg_pct: 2.10 },
    { name: '医药', chg_pct: -0.66, net: -3.2, leader: '迈瑞医疗', leader_chg_pct: 0.30 },
    { name: '计算机', chg_pct: 2.45, net: 14.7, leader: '海康威视', leader_chg_pct: 2.80 },
    { name: '汽车', chg_pct: 0.42, net: 2.1, leader: '比亚迪', leader_chg_pct: -2.40 },
  ],
  src_label: '行业资金流(akshare)',
  unavailable: [],
  date: null,
}

// 智能盯盘（watch）Mock：只读聚合自选股主力资金流 + 板块异动 + 资金流预警。
// 金额单位=亿元（与后端 _ff_yi 一致），null = 字段缺失。以下数值为演示、非真实行情。
export const watch = {
  watchlist: [
    { code: '600519', name: '贵州茅台', note: '核心持仓', fund: { source: 'akshare', main_net: 5.0, main_net_pct: 4.2, big_net: 3.0, super_net: 2.0, latest_date: '2026-11-10' } },
    { code: '000001', name: '平安银行', note: '', fund: { source: 'estimate', main_net: -2.0, main_net_pct: -3.5, big_net: null, super_net: null, latest_date: '2026-11-10' } },
    { code: '300750', name: '宁德时代', note: '观察', fund: { source: 'akshare', main_net: 8.4, main_net_pct: 2.1, big_net: 5.0, super_net: 3.4, latest_date: '2026-11-10' } },
  ],
  sector_items: [
    { name: '半导体', chg_pct: 3.52, net: 18.6, leader: '中微公司', leader_chg_pct: 6.21 },
    { name: '白酒', chg_pct: -1.24, net: -5.3, leader: '贵州茅台', leader_chg_pct: -0.52 },
    { name: '银行', chg_pct: 0.81, net: 12.4, leader: '招商银行', leader_chg_pct: 1.12 },
    { name: '军工', chg_pct: 2.07, net: 7.8, leader: '中航沈飞', leader_chg_pct: 3.44 },
    { name: '新能源', chg_pct: 1.93, net: 9.1, leader: '宁德时代', leader_chg_pct: 2.10 },
    { name: '医药', chg_pct: -0.66, net: -3.2, leader: '迈瑞医疗', leader_chg_pct: 0.30 },
  ],
  alerts: [
    { code: '600519', name: '贵州茅台', level: '强', reason: '主力净流入占比 +4.20%（强）' },
    { code: '000001', name: '平安银行', level: '弱', reason: '主力净流出占比 -3.50%（弱）' },
    { code: '300750', name: '宁德时代', level: '中性', reason: '主力净流入占比 +2.10%（中性）' },
  ],
  summary: { watch_count: 3, with_fund: 3, strong_count: 1, weak_count: 1, sector_available: true },
  src_labels: { watchlist_fund: '个股主力资金流(akshare/估算)', sector: '行业资金流(akshare)' },
  unavailable: [],
  note: '本页为 V2 只读盯盘聚合：自选股 + 板块资金异动 + 逐只个股主力资金流。实时现价/涨跌幅未在此只读端点聚合（实时行情取数依赖 Streamlit 单例，Flask 上下文不可用），需看实时价请用个股分时/行情端点或 v1 盯盘页；资金流预警基于主力净流入占比阈值，非价格。数据为加载时点快照，非实时，非投资建议。',
}

// 行情看板（quote-board）Mock：指数（日线快照，日期为权威数据日）+ 行业板块涨跌榜
// + 市场状态（服务器时间真实计算的样例）。null = 该字段取不到，数值为演示、非真实行情。
export const quoteBoard = {
  indices: [
    { code: 'sh000001', name: '上证指数', current: 3955.9, prev_close: 3946.2, change: 9.7, change_pct: 0.25, date: '2026-11-11' },
    { code: 'sz399001', name: '深证成指', current: 13210.4, prev_close: 13188.5, change: 21.9, change_pct: 0.17, date: '2026-11-11' },
    { code: 'sz399006', name: '创业板指', current: 2785.6, prev_close: 2801.2, change: -15.6, change_pct: -0.56, date: '2026-11-11' },
    { code: 'sh000016', name: '上证50', current: 2688.3, prev_close: 2680.1, change: 8.2, change_pct: 0.31, date: '2026-11-11' },
    { code: 'sh000300', name: '沪深300', current: 4621.7, prev_close: 4612.4, change: 9.3, change_pct: 0.2, date: '2026-11-11' },
  ],
  sectors: [
    { name: '半导体', chg_pct: 3.52, net: 18.6, leader: '中微公司', leader_chg_pct: 6.21 },
    { name: '计算机', chg_pct: 2.45, net: 14.7, leader: '海康威视', leader_chg_pct: 2.80 },
    { name: '军工', chg_pct: 2.07, net: 7.8, leader: '中航沈飞', leader_chg_pct: 3.44 },
    { name: '银行', chg_pct: 0.81, net: 12.4, leader: '招商银行', leader_chg_pct: 1.12 },
    { name: '医药', chg_pct: -0.66, net: -3.2, leader: '迈瑞医疗', leader_chg_pct: 0.30 },
    { name: '白酒', chg_pct: -1.24, net: -5.3, leader: '贵州茅台', leader_chg_pct: -0.52 },
  ],
  market_status: { is_open: true, text: '🟢 下午交易中', refresh_ms: 60000 },
  summary: { index_count: 5, index_available: 5, sector_count: 6, sector_available: true },
  src_labels: { indices: '主要指数(akshare 日线)', sectors: '行业资金流(akshare)' },
  unavailable: [],
  note: '本页为 V2 只读行情看板：主要指数（akshare 日线，离线返回确定性静态样例）+ 行业板块涨跌榜（行业资金流）+ 市场状态（基于服务器北京时间）。指数为页面加载时点快照（日线级），非实时逐笔；数据为加载时点快照，非实时，非投资建议。',
}

// W4-A · 个股六维评分（six-dim）Mock，字段名与后端契约一致，数值为演示、非真实行情。
// 六维键固定顺序 technical/capital/value/growth/fundamental/cycle；null = 该维取数失败。
// sixDimFull：6 维齐全、date 有权威数据日；sixDimPartial：capital/growth 缺失、date 为 null。
// ⚠️ 缺失与空数据日如实保留，禁止补 0 / 禁止用当前日期兜底。
export const sixDimFull = {
  code: '600519',
  dims: {
    technical: 72.5,
    capital: 68.0,
    value: 61.0,
    growth: 57.4,
    fundamental: 55.3,
    cycle: 48.0,
  },
  overall: 60.4,
  coverage: 6,
  missing: [],
  date: '2026-11-07',
  raw: {
    pe: 28.1, pb: 8.2, roe: 24.3, profit_yoy: 12.6, state: null,
    turnover: 1.8, vol_ratio: 0.9, pos60: 3.4,
  },
  note: '逐维独立取数、独立降级；缺失维为 null 且不参与 overall 平均',
}

export const sixDimPartial = {
  code: '000001',
  dims: {
    technical: 50.2,
    capital: null,
    value: 44.8,
    growth: null,
    fundamental: 39.1,
    cycle: 41.6,
  },
  overall: 43.9,
  coverage: 4,
  missing: ['capital', 'growth'],
  date: null,
  raw: {
    pe: 5.6, pb: 0.5, roe: null, profit_yoy: null, state: null,
    turnover: null, vol_ratio: null, pos60: -1.2,
  },
  note: '逐维独立取数、独立降级；缺失维为 null 且不参与 overall 平均',
}

// ═══════════════════ W4-B · 个股域三端点 Mock（演示数值、非真实行情）═══════════════════
// 字段名严格对齐 backend/api/read_routes.py:957-1058 的 fundamentals / financials / stock-kline。
// 每端点备 4 形态：完整 / 全字段 null 降级 / rows 空(或 perf 整体 null) / date:null。
// handlers 按 code query 分派：
//   600519 → 完整
//   000002 → 全源失败态：perf 为 9 字段全 null 的「对象」(后端实测形态)、各标量 null、date:null
//   000003 → perf 整体 null（Zod .nullable() 保守上界兼容形态）/ rows 空（financials、stock-kline）
//   000004 → date:null（其余字段完整，专测「暂无权威数据日」且禁止今天日期兜底）
// ⚠️ 缺失与空数据日如实保留，禁止补 0 / 禁止用当前日期兜底。
const W4B_NOTE = '逐字段独立取数、独立降级；缺失为 null 且不补 0'

const w4bPerfFull = {
  revenue_yi: 1234.56,
  revenue_yoy: 12.34,
  net_profit_yi: 567.89,
  profit_yoy: 8.76,
  gross_margin: 91.2,
  roe: 24.3,
  alr: 17.5,
  current_ratio: 3.8,
  equity_ratio: 82.5,
}

const w4bPerfAllNull = {
  revenue_yi: null,
  revenue_yoy: null,
  net_profit_yi: null,
  profit_yoy: null,
  gross_margin: null,
  roe: null,
  alr: null,
  current_ratio: null,
  equity_ratio: null,
}

// ── fundamentals（旧 22 页）──
export const fundamentalsFull = {
  code: '600519',
  name: '贵州茅台',
  industry: '白酒',
  price: 1523.5,
  pe_ttm: 28.1,
  market_cap: 19138.2,
  spot_date: '2026-11-06',
  kline_date: '2026-11-05',
  perf: w4bPerfFull,
  priceDomain: 'market',
  date: '2026-11-06',
  note: W4B_NOTE,
}

export const fundamentalsNullFields = {
  code: '000002',
  name: null,
  industry: null,
  price: null,
  pe_ttm: null,
  market_cap: null,
  spot_date: null,
  kline_date: null,
  perf: w4bPerfAllNull,
  priceDomain: 'market',
  date: null,
  note: null,
}

export const fundamentalsPerfNull = {
  ...fundamentalsFull,
  code: '000003',
  perf: null,
}

export const fundamentalsDateNull = {
  ...fundamentalsFull,
  code: '000004',
  date: null,
}

// ── financials（多期财报，中文动态列名，含 _同比/_环比）──
const w4bFinRows = [
  { 报告期: '2025-09-30', 标签: '2025 三季', 营业总收入: 1231.23, 归母净利润: 608.76, 净资产收益率: 24.6, 营业总收入_同比: 15.3, 归母净利润_同比: 15.1 },
  { 报告期: '2025-06-30', 标签: '2025 中报', 营业总收入: 910.94, 归母净利润: 454.03, 净资产收益率: 18.2, 营业总收入_同比: 9.2, 归母净利润_同比: 8.9 },
]

export const financialsFull = {
  code: '600519',
  report: 'income',
  rows: w4bFinRows,
  date: '2025-09-30',
  note: W4B_NOTE,
}

export const financialsNullFields = {
  code: '000002',
  report: 'income',
  rows: [{ 报告期: '2025-09-30', 营业总收入: null, 归母净利润: null, 净资产收益率: null, 营业总收入_同比: null }],
  date: null,
  note: null,
}

export const financialsEmptyRows = {
  code: '000003',
  report: 'income',
  rows: [],
  date: null,
  note: W4B_NOTE,
}

export const financialsDateNull = {
  ...financialsFull,
  code: '000004',
  date: null,
}

// ── stock-kline（OHLC，英文列原样透出）──
const w4bKlineRows = [
  { date: '2026-11-06', open: 1510.0, high: 1535.5, low: 1502.3, close: 1523.5, volume: 32100 },
  { date: '2026-11-05', open: 1498.0, high: 1518.0, low: 1490.0, close: 1508.0, volume: 28700 },
  { date: '2026-11-04', open: 1505.0, high: 1510.0, low: 1492.0, close: 1499.5, volume: 25400 },
]

export const klineFull = {
  code: '600519',
  period: 'daily',
  rows: w4bKlineRows,
  date: '2026-11-06',
  note: W4B_NOTE,
}

export const klineNullFields = {
  code: '000002',
  period: 'daily',
  rows: [{ date: '2026-11-06', open: null, high: null, low: null, close: null, volume: null }],
  date: null,
  note: null,
}

export const klineEmptyRows = {
  code: '000003',
  period: 'daily',
  rows: [],
  date: null,
  note: W4B_NOTE,
}

export const klineDateNull = {
  ...klineFull,
  code: '000004',
  date: null,
}

// ═══════════════════ W4-C · 多股对比 / 深度分析 / 分时 三端点 Mock ═══════════════════
// 字段名对齐后端 read_routes 契约（通用透传，前端按 key 渲染）；数值为演示、非真实行情。
// 降级语义与 W4-B 同款 4 态：完整 / 全源失败(全 null) / 空(仅 code) / date:null。

// compare-one：单股通用对比快照（混合价格域 + 业绩域字段，演示数值）。
export const compareOneFull = {
  code: '600519',
  name: '贵州茅台',
  industry: '白酒',
  price: 1523.5,
  change_pct: 1.24,
  pct_chg: 1.24,
  open: 1505.0,
  high: 1535.5,
  low: 1502.3,
  pre_close: 1504.3,
  volume: 32100,
  amount: 48.6,
  pe: 28.1,
  pb: 8.2,
  ps: 12.4,
  market_cap: 19138.2,
  turnover: 0.42,
  amplitude: 2.21,
  ma5: 1508.7,
  ma10: 1498.2,
  ma20: 1476.5,
  ma60: 1421.0,
  rsi: 63.4,
  macd: 12.3,
  kdj: 78.1,
  boll: 1499.0,
  revenue_yoy: 12.34,
  profit_yoy: 8.76,
  growth: 9.10,
  roe: 24.3,
  gross_margin: 91.2,
  date: '2026-11-06',
  note: W4B_NOTE,
}

// 全源失败态：所有指标字段为 null（与 W4-B fundamentalsNullFields 同款语义）。
export const compareOneNullFields = {
  code: '000002',
  name: null,
  industry: null,
  price: null,
  change_pct: null,
  pct_chg: null,
  open: null,
  high: null,
  low: null,
  pre_close: null,
  volume: null,
  amount: null,
  pe: null,
  pb: null,
  ps: null,
  market_cap: null,
  turnover: null,
  amplitude: null,
  ma5: null,
  ma10: null,
  ma20: null,
  ma60: null,
  rsi: null,
  macd: null,
  kdj: null,
  boll: null,
  revenue_yoy: null,
  profit_yoy: null,
  growth: null,
  roe: null,
  gross_margin: null,
  date: null,
  note: null,
}

// 空态：仅 code，无任何指标字段（前端按 empty 渲染「暂无对比数据」）。
export const compareOneEmpty = {
  code: '000003',
}

// date:null 态：其余字段完整，专测「暂无权威数据日」且不兜底今天。
export const compareOneDateNull = {
  ...compareOneFull,
  code: '000004',
  date: null,
}

// research-deep：技术字段快照（通用透传，前端按 key 渲染技术字段表）。
// ⚠️ 真后端 read_routes.research_deep() 恒返回 deep_analysis_available=false
// （56 键 analysis_engine 异步分析本轮未接入）；MSW 必须一致，不得伪造「已接入」。
// true 分支仅由组件测试显式注入响应覆盖，不是任何真实/MSW 端点的返回。
export const researchDeepFull = {
  code: '600519',
  name: '贵州茅台',
  deep_analysis_available: false,
  price: 1523.5,
  pe_ttm: 28.1,
  pb: 8.2,
  market_cap: 19138.2,
  ma5: 1508.7,
  ma10: 1498.2,
  ma20: 1476.5,
  ma60: 1421.0,
  amplitude: 2.21,
  turnover: 0.42,
  rsi: 63.4,
  macd: 12.3,
  kdj: 78.1,
  boll: 1499.0,
  revenue_yoy: 12.34,
  profit_yoy: 8.76,
  roe: 24.3,
  gross_margin: 91.2,
  date: '2026-11-06',
  note: '深度分析为旧版 analysis_engine 异步任务结果透传',
}

// 豁免态：明确未接入（前端显示「56 键深度分析 V2 暂未接入，可走 /legacy 查看旧版」）。
export const researchDeepExempt = {
  code: '000003',
  name: '海康威视',
  deep_analysis_available: false,
  date: null,
  note: null,
}

// stock-intraday：分时明细（英文列原样透出，与后端 read_routes._w4c_intraday 同形）。
// ⚠️ 列名以**后端透出形状**为准（time/open/high/low/close/volume/amount），
//    均价由前端按「累计成交额/累计成交量」算（后端不返回均价）。
const w4cIntradayRows = [
  { time: '2026-11-06 09:31:00', open: 1519.8, high: 1521.4, low: 1519.2, close: 1520.9, volume: 1200, amount: 1825080 },
  { time: '2026-11-06 09:32:00', open: 1520.9, high: 1524.6, low: 1520.1, close: 1523.8, volume: 1800, amount: 2742840 },
  { time: '2026-11-06 09:33:00', open: 1523.8, high: 1526.0, low: 1522.4, close: 1525.5, volume: 1500, amount: 2288250 },
  { time: '2026-11-06 09:34:00', open: 1525.5, high: 1526.8, low: 1521.7, close: 1522.3, volume: 2100, amount: 3196830 },
  { time: '2026-11-06 09:35:00', open: 1522.3, high: 1523.1, low: 1518.4, close: 1519.2, volume: 2600, amount: 3949920 },
]

/** 分时（含昨收基准）：600519 有昨收 → 前端画昨收基准虚线。 */
export const stockIntradayFull = {
  code: '600519',
  period: 'intraday',
  rows: w4cIntradayRows,
  date: '2026-11-06',
  prev_close: 1520.0,
  note: W4B_NOTE,
}

/**
 * 分时（**无昨收基准**）：底层取不到昨收 → prev_close 为 null，
 * 前端据此不画基准线并如实标注「暂无昨收基准」（绝不拿首笔开盘冒充昨收）。
 */
export const stockIntradayNoPrevClose = {
  code: '000002',
  period: 'intraday',
  rows: w4cIntradayRows.map((r) => ({ ...r })),
  date: '2026-11-06',
  prev_close: null,
  note: W4B_NOTE,
}

// ───────── 指数行情（index-quotes / index-kline）开发期样例 ─────────
// 仅 MSW 开发态使用；值为确定性静态样例（非实时），与后端离线降级口径一致：缺失即 null。
const w4xIndexKlineRows = [
  { date: '2026-11-02', open: 3890.5, high: 3912.3, low: 3885.1, close: 3904.2, volume: 312_000_000 },
  { date: '2026-11-03', open: 3905.0, high: 3928.7, low: 3901.4, close: 3921.6, volume: 338_000_000 },
  { date: '2026-11-04', open: 3920.8, high: 3935.2, low: 3912.9, close: 3910.3, volume: 305_000_000 },
  { date: '2026-11-05', open: 3911.0, high: 3942.8, low: 3908.6, close: 3936.1, volume: 356_000_000 },
  { date: '2026-11-06', open: 3937.4, high: 3955.0, low: 3933.2, close: 3948.8, volume: 372_000_000 },
  { date: '2026-11-09', open: 3950.1, high: 3968.4, low: 3941.7, close: 3960.5, volume: 389_000_000 },
  { date: '2026-11-10', open: 3961.0, high: 3972.9, low: 3948.3, close: 3946.2, volume: 341_000_000 },
  { date: '2026-11-11', open: 3945.0, high: 3961.6, low: 3938.4, close: 3955.9, volume: 328_000_000 },
]

/** index-quotes：主要指数报价（外部卡片视角）。current/change/change_pct 为样例值。 */
export const indexQuotes = {
  items: [
    { code: 'sh000001', name: '上证指数', current: 3955.9, prev_close: 3946.2, change: 9.7, change_pct: 0.25, date: '2026-11-11' },
    { code: 'sz399001', name: '深证成指', current: 13210.4, prev_close: 13188.5, change: 21.9, change_pct: 0.17, date: '2026-11-11' },
    { code: 'sz399006', name: '创业板指', current: 2785.6, prev_close: 2801.2, change: -15.6, change_pct: -0.56, date: '2026-11-11' },
    { code: 'sh000016', name: '上证50', current: 2688.3, prev_close: 2680.1, change: 8.2, change_pct: 0.31, date: '2026-11-11' },
    { code: 'sh000300', name: '沪深300', current: 4621.7, prev_close: 4612.4, change: 9.3, change_pct: 0.2, date: '2026-11-11' },
  ],
  note: W4B_NOTE,
}

/** index-kline（sh000001 样例）：点击卡片弹窗的 K 线数据源。 */
export const indexKlineSh000001 = {
  code: 'sh000001',
  rows: w4xIndexKlineRows,
  date: '2026-11-11',
  note: W4B_NOTE,
}

// ───────── 数据源 / 接口检测（diagnostics）开发期样例 ─────────
// 仅 MSW 开发态使用；值为确定性静态样例（非实时），与后端离线降级口径一致：缺失即 null。
const diagNote =
  '数据源检测只读本地文件与缓存库（默认不触网）；接口检测由前端对真实注册端点逐个发起 GET 请求并记录 HTTP 状态与耗时。任一检测失败如实标注，不做成功假定、不补 0。'

/** 只读端点清单样例（真后端由 Flask url_map 动态枚举，此处仅为开发态代表集）。 */
// 形态必须与后端 _diag_endpoints() 一致：需参端点 needs_params=true、
// probe_path=null（不得把带 query 的路径伪装成「可直接探测」端点），
// sample_query 是合法示例参数，UI 会标注它不是真实业务数据。
export const diagnosticsEndpoints = [
  { path: '/api/v2/read/daily-snapshot', needs_params: false, probe_path: '/api/v2/read/daily-snapshot', required_query: [], sample_query: null },
  { path: '/api/v2/read/snapshot-dates', needs_params: false, probe_path: '/api/v2/read/snapshot-dates', required_query: [], sample_query: null },
  { path: '/api/v2/read/p1-sync-status', needs_params: false, probe_path: '/api/v2/read/p1-sync-status', required_query: [], sample_query: null },
  { path: '/api/v2/read/data-refresh-state', needs_params: false, probe_path: '/api/v2/read/data-refresh-state', required_query: [], sample_query: null },
  { path: '/api/v2/read/index-quotes', needs_params: false, probe_path: '/api/v2/read/index-quotes', required_query: [], sample_query: null },
  { path: '/api/v2/read/diagnostics', needs_params: false, probe_path: '/api/v2/read/diagnostics', required_query: [], sample_query: null },
  { path: '/api/v2/read/backtest-runs', needs_params: false, probe_path: '/api/v2/read/backtest-runs', required_query: [], sample_query: null },
  { path: '/api/v2/read/snapshot/<date>', needs_params: true, probe_path: null, required_query: ['<path>'], sample_query: null },
  { path: '/api/v2/read/six-dim', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=600519' },
  { path: '/api/v2/read/financials', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=600519' },
  { path: '/api/v2/read/paper-trades', needs_params: true, probe_path: null, required_query: ['user'], sample_query: 'user=admin' },
  { path: '/api/v2/read/index-kline', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=sh000001' },
  { path: '/api/v2/read/review-notes', needs_params: true, probe_path: null, required_query: ['date'], sample_query: 'date=2026-09-21' },
  { path: '/api/v2/read/fundamentals', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=600519' },
  { path: '/api/v2/read/stock-kline', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=600519' },
  { path: '/api/v2/read/compare-one', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=600519' },
  { path: '/api/v2/read/research-deep', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=600519' },
  { path: '/api/v2/read/stock-intraday', needs_params: true, probe_path: null, required_query: ['code'], sample_query: 'code=600519' },
  { path: '/api/v2/read/factor-analysis', needs_params: false, probe_path: '/api/v2/read/factor-analysis', required_query: [], sample_query: null },
  { path: '/api/v2/read/backtest', needs_params: true, probe_path: null, required_query: ['ticker'], sample_query: 'ticker=600519&start=2024-01-01&end=2024-12-31&strategy=multi_factor' },
  { path: '/api/v2/read/market-panorama', needs_params: false, probe_path: '/api/v2/read/market-panorama', required_query: [], sample_query: null },
  { path: '/api/v2/read/portfolio', needs_params: false, probe_path: '/api/v2/read/portfolio', required_query: [], sample_query: null },
  { path: '/api/v2/read/fund-flow', needs_params: false, probe_path: '/api/v2/read/fund-flow', required_query: [], sample_query: null },
  { path: '/api/v2/read/trading-account', needs_params: false, probe_path: '/api/v2/read/trading-account', required_query: [], sample_query: null },
  { path: '/api/v2/read/macro-data', needs_params: false, probe_path: '/api/v2/read/macro-data', required_query: [], sample_query: null },
  { path: '/api/v2/read/dragon-tiger', needs_params: false, probe_path: '/api/v2/read/dragon-tiger', required_query: [], sample_query: null },
  { path: '/api/v2/read/theme', needs_params: false, probe_path: '/api/v2/read/theme', required_query: [], sample_query: null },
  { path: '/api/v2/read/theme-transmission', needs_params: false, probe_path: '/api/v2/read/theme-transmission', required_query: [], sample_query: null },
  { path: '/api/v2/read/strong', needs_params: false, probe_path: '/api/v2/read/strong', required_query: [], sample_query: null },
  { path: '/api/v2/read/sector-rotation', needs_params: false, probe_path: '/api/v2/read/sector-rotation', required_query: [], sample_query: null },
  { path: '/api/v2/read/watch', needs_params: false, probe_path: '/api/v2/read/watch', required_query: [], sample_query: null },
  { path: '/api/v2/read/quote-board', needs_params: false, probe_path: '/api/v2/read/quote-board', required_query: [], sample_query: null },
  { path: '/api/v2/read/breadth-analytics', needs_params: false, probe_path: '/api/v2/read/breadth-analytics', required_query: [], sample_query: null },
  { path: '/api/v2/read/breadth-zseries', needs_params: true, probe_path: null, required_query: ['dim'], sample_query: 'dim=up_count' },
  { path: '/api/v2/read/limit-up-review', needs_params: false, probe_path: '/api/v2/read/limit-up-review', required_query: [], sample_query: null },
  { path: '/api/v2/read/market-sentiment', needs_params: false, probe_path: '/api/v2/read/market-sentiment', required_query: [], sample_query: null },
  { path: '/api/v2/read/momentum-breadth', needs_params: false, probe_path: '/api/v2/read/momentum-breadth', required_query: [], sample_query: null },
]

export const diagnostics = {
  sources: {
    available: true,
    summary: '4/5 可用',
    checked_at: '2026-11-08 22:30:00',
    items: [
      { key: 'akshare', label: 'akshare', ok: true, detail: '依赖可用 (1.16.x)', tables: null },
      { key: 'baostock', label: 'BaoStock', ok: false, detail: '依赖缺失', tables: null },
      { key: 'sina', label: '新浪财经', ok: true, detail: 'fetcher 就绪', tables: null },
      { key: 'eastmoney', label: '东方财富', ok: true, detail: 'fetcher 就绪', tables: null },
      { key: 'cache', label: '本地缓存', ok: true, detail: '6 表 / 12,345 条', tables: { kline: 8000, quote: 4345 } },
    ],
    reason: null,
  },
  freshness: {
    available: true,
    rows: [
      { key: 'daily_snapshot', name: '每日快照', as_of: '2026-11-06', lag_days: 2, status: 'ok' },
      { key: 'p1_event', name: 'P1 事件因子', as_of: '2026-10-16', lag_days: 23, status: 'stale' },
      { key: 'shepherd_sentiment', name: '牧羊人情绪', as_of: '2026-11-06', lag_days: 2, status: 'ok' },
      { key: 'market_temp', name: '市场温度', as_of: null, lag_days: null, status: 'unknown' },
    ],
    reason: null,
  },
  endpoints: diagnosticsEndpoints,
  probe: null,
  note: diagNote,
}

/** probe=1 探测结果样例：四源如实含一失败项，不美化。 */
export const diagnosticsProbe = {
  ...diagnostics,
  probe: {
    available: true,
    levels: [
      { level: 'L1', ok: true, detail: '30 行 / 600519', latency_ms: 176 },
      { level: 'L2', ok: false, detail: '依赖缺失', latency_ms: -1 },
      { level: 'L3', ok: true, detail: '30 行 / 600519', latency_ms: 312 },
      { level: 'L4', ok: false, detail: '连接超时', latency_ms: 10000 },
    ],
    reason: null,
  },
}

/** 数据源检测整体失败态（available=false，不得包装成「全部可用」）。 */
export const diagnosticsDegraded = {
  ...diagnostics,
  sources: {
    available: false,
    summary: null,
    checked_at: null,
    items: [],
    reason: 'RuntimeError: 模拟 fetcher 不可用',
  },
  freshness: {
    available: false,
    rows: [],
    reason: 'OSError: 模拟本地文件不可读',
  },
  probe: null,
}

// ───────── 管理端（用户管理 / 操作日志，92 页 V2 化）─────────
// 结构对齐 backend/models.py::User.to_public / OperationLog.to_dict；数值为演示。
// 初始管理员 id=1、username='admin'（与前端「不能删自己 / 不能删初始 admin」规则同源）。
export const adminUsers = [
  {
    id: 1,
    username: 'admin',
    role: 'admin',
    created_at: '2026-01-01T08:00:00Z',
    is_active: true,
    avatar: null,
    settings: {},
  },
  {
    id: 2,
    username: 'demo',
    role: 'user',
    created_at: '2026-03-12T10:24:00Z',
    is_active: true,
    avatar: null,
    settings: {},
  },
  {
    id: 3,
    username: 'guest',
    role: 'user',
    created_at: '2026-06-20T14:05:00Z',
    is_active: false,
    avatar: null,
    settings: {},
  },
]

export const adminLogs = [
  {
    id: 1,
    user_id: 1,
    username: 'admin',
    action: 'create_user',
    target: 'demo',
    detail: 'role=user',
    created_at: '2026-03-12T10:24:00Z',
  },
  {
    id: 2,
    user_id: 1,
    username: 'admin',
    action: 'update_user',
    target: 'guest',
    detail: 'is_active=false',
    created_at: '2026-06-20T14:10:00Z',
  },
  {
    id: 3,
    user_id: 2,
    username: 'demo',
    action: 'update_user',
    target: 'demo',
    detail: 'password=***',
    created_at: '2026-07-02T09:15:00Z',
  },
]

// ───────── 我的（91 页 v2 /me）：自定义看板偏好种子（对齐 data/user_dashboard.json）─────────
export const userDashboard = {
  default_widgets: ['snapshot', 'recommendation', 'breadth', 'event', 'backtest'],
  note: '73 自定义看板默认组件种子；用户实际选择由前端 localStorage 持久化，不依赖此文件。',
  updated_at: '2026-11-11',
}

// ───────── 财报日历（16 页 v2 /earnings-calendar）：对齐真后端规整后的契约列 ─────────
// ⚠️ 形态必须与 /api/v2/read/earnings-calendar 真实输出一致：akshare 原始列
// （股票代码/股票简称/首次预约/实际披露）+ 端点规整列（报告期/披露时间/披露状态）。
// 历史缺陷（2026-11-11）：夹具曾用「预约披露日期/披露日期」旧列名，与真后端
// 「首次预约/实际披露」不一致，MSW 全绿却掩盖了接真后端时三列全显「—」。
export const earningsCalendar = {
  market: '沪深京',
  period: '2025年报',
  date: '2026-04-15', // 「实际披露」最大值（未披露行不计），与端点 date 口径一致
  unavailable: false,
  note: '数据来源：东方财富 财报预约披露日历（年报）',
  rows: [
    { 股票代码: '600519', 股票简称: '贵州茅台', 首次预约: '2026-03-31T00:00:00.000', 实际披露: '2026-03-31T00:00:00.000', 报告期: '2025年报', 披露时间: '2026-03-31', 披露状态: '已披露' },
    { 股票代码: '000001', 股票简称: '平安银行', 首次预约: '2026-03-20T00:00:00.000', 实际披露: '2026-03-20T00:00:00.000', 报告期: '2025年报', 披露时间: '2026-03-20', 披露状态: '已披露' },
    { 股票代码: '300750', 股票简称: '宁德时代', 首次预约: '2026-04-15T00:00:00.000', 实际披露: '2026-04-15T00:00:00.000', 报告期: '2025年报', 披露时间: '2026-04-15', 披露状态: '已披露' },
    { 股票代码: '601318', 股票简称: '中国平安', 首次预约: '2026-03-25T00:00:00.000', 实际披露: '2026-03-25T00:00:00.000', 报告期: '2025年报', 披露时间: '2026-03-25', 披露状态: '已披露' },
    { 股票代码: '600036', 股票简称: '招商银行', 首次预约: '2026-03-28T00:00:00.000', 实际披露: '2026-03-28T00:00:00.000', 报告期: '2025年报', 披露时间: '2026-03-28', 披露状态: '已披露' },
    { 股票代码: '000333', 股票简称: '美的集团', 首次预约: '2026-04-30T00:00:00.000', 实际披露: null, 报告期: '2025年报', 披露时间: '2026-04-30', 披露状态: '预约待披露' },
  ],
}

// ───────── 离线可靠广度统计（65/67/68/69 页 v2 native，2026-11-11 真端点 dump）
// ⚠️ 字段形态来自隔离库真跑 /api/v2/read/breadth-analytics 与 /breadth-zseries 的响应，
// 数值为 data/shepherd_history.json 真实离线序列的**末 60 日子集**（非编造演示数）。
// 真后端按 window 返回 60/120/250/750/2000 日；MSW 仅回放这 60 日，handler 会把
// window 如实回显为实际点数，页面按此标注，绝不假装拿到了更长历史。
export const breadthAnalytics = {
  "data_as_of": "2026-08-21",
  "window": 60,
  "reliable_dims": [
    "up_count",
    "down_count",
    "flat_count",
    "limit_up",
    "limit_down",
    "red_ratio"
  ],
  "reliable_labels": {
    "up_count": "上涨家数",
    "down_count": "下跌家数",
    "flat_count": "平盘家数",
    "limit_up": "涨停家数",
    "limit_down": "跌停家数",
    "red_ratio": "红盘占比(%)"
  },
  "offline_missing": {
    "connect_hl": "连板高度（离线健康镜像 99.7% 为 NaN）",
    "connect_2b": "连板家数≥2板（离线镜像无此字段，被填 0）",
    "zt_fail_ratio": "炸板率（离线健康镜像 99.7% 为 NaN）",
    "fc_ratio": "平均封成比（离线镜像无此字段，被填 0）",
    "zt_prev_ret": "昨日涨停表现（离线健康镜像 99.7% 为 NaN）",
    "touch_down": "倒跌停家数（离线镜像无此字段，被填 0）",
    "median_chg": "中位数涨跌幅（离线镜像无此字段，被填 0）",
    "hb_wave10": "回头波>10%家数（离线镜像无此字段，被填 0）",
    "avg_price": "平均股价（离线镜像无此字段，被填 0）",
    "turnover_amt": "全A成交额（离线镜像无此字段，被填 0）"
  },
  "note": "统计基于离线健康镜像真值，仅用可靠字段；均为历史描述，不预测收益。",
  "sections": {
    "phase": {
      "current": {
        "available": true,
        "date": "2026-08-21",
        "red_ratio": 46.67287977632805,
        "limit_up": 54.0,
        "limit_down": 13.0,
        "red_ratio_pct": 0.461,
        "limit_up_pct": 0.761,
        "phase": "中性",
        "reason": "未触发极端相位，投机情绪中性"
      },
      "series": {
        "available": true,
        "dates": [
          "2026-05-29",
          "2026-06-01",
          "2026-06-02",
          "2026-06-03",
          "2026-06-04",
          "2026-06-05",
          "2026-06-08",
          "2026-06-09",
          "2026-06-10",
          "2026-06-11",
          "2026-06-12",
          "2026-06-15",
          "2026-06-16",
          "2026-06-17",
          "2026-06-18",
          "2026-06-22",
          "2026-06-23",
          "2026-06-24",
          "2026-06-25",
          "2026-06-26",
          "2026-06-29",
          "2026-06-30",
          "2026-07-01",
          "2026-07-02",
          "2026-07-03",
          "2026-07-06",
          "2026-07-07",
          "2026-07-08",
          "2026-07-09",
          "2026-07-10",
          "2026-07-13",
          "2026-07-14",
          "2026-07-15",
          "2026-07-16",
          "2026-07-17",
          "2026-07-20",
          "2026-07-21",
          "2026-07-22",
          "2026-07-23",
          "2026-07-24",
          "2026-07-27",
          "2026-07-28",
          "2026-07-29",
          "2026-07-30",
          "2026-07-31",
          "2026-08-03",
          "2026-08-04",
          "2026-08-05",
          "2026-08-06",
          "2026-08-07",
          "2026-08-10",
          "2026-08-11",
          "2026-08-12",
          "2026-08-13",
          "2026-08-14",
          "2026-08-17",
          "2026-08-18",
          "2026-08-19",
          "2026-08-20",
          "2026-08-21"
        ],
        "series": {
          "limit_up": [
            52.0,
            122.0,
            70.0,
            70.0,
            81.0,
            77.0,
            59.0,
            133.0,
            71.0,
            77.0,
            98.0,
            157.0,
            122.0,
            91.0,
            94.0,
            143.0,
            100.0,
            101.0,
            92.0,
            60.0,
            110.0,
            145.0,
            159.0,
            93.0,
            109.0,
            74.0,
            34.0,
            58.0,
            75.0,
            97.0,
            33.0,
            90.0,
            75.0,
            51.0,
            35.0,
            58.0,
            128.0,
            49.0,
            130.0,
            44.0,
            122.0,
            68.0,
            86.0,
            57.0,
            105.0,
            75.0,
            138.0,
            103.0,
            79.0,
            74.0,
            99.0,
            58.0,
            92.0,
            59.0,
            63.0,
            106.0,
            79.0,
            36.0,
            79.0,
            54.0
          ],
          "limit_down": [
            57.0,
            27.0,
            15.0,
            12.0,
            8.0,
            14.0,
            38.0,
            10.0,
            26.0,
            36.0,
            20.0,
            4.0,
            7.0,
            1.0,
            19.0,
            5.0,
            50.0,
            10.0,
            22.0,
            42.0,
            42.0,
            10.0,
            11.0,
            48.0,
            28.0,
            57.0,
            57.0,
            56.0,
            17.0,
            10.0,
            210.0,
            31.0,
            48.0,
            47.0,
            238.0,
            295.0,
            31.0,
            11.0,
            3.0,
            30.0,
            6.0,
            60.0,
            15.0,
            101.0,
            0.0,
            8.0,
            0.0,
            1.0,
            1.0,
            4.0,
            5.0,
            1.0,
            0.0,
            4.0,
            10.0,
            1.0,
            5.0,
            118.0,
            12.0,
            13.0
          ],
          "red_ratio": [
            28.355,
            69.211,
            28.482,
            31.505,
            24.583,
            60.777,
            16.332,
            61.922,
            28.656,
            25.143,
            72.147,
            72.563,
            50.5,
            31.548,
            37.308,
            54.204,
            51.157,
            26.222,
            22.52,
            14.38,
            45.653,
            56.319,
            79.068,
            41.187,
            70.057,
            34.677,
            12.634,
            29.557,
            46.256,
            69.208,
            14.546,
            77.14,
            61.495,
            46.611,
            8.776,
            31.92,
            57.476,
            28.281,
            77.9,
            10.089,
            94.796,
            48.454,
            77.786,
            32.698,
            86.563,
            73.213,
            67.589,
            69.699,
            51.823,
            52.968,
            74.514,
            29.905,
            76.341,
            20.92,
            44.701,
            80.304,
            39.161,
            8.089,
            75.262,
            46.673
          ],
          "up_count": [
            1536.0,
            3772.0,
            1542.0,
            1712.0,
            1342.0,
            3271.0,
            895.0,
            3319.0,
            1556.0,
            1366.0,
            3919.0,
            3901.0,
            2727.0,
            1720.0,
            2018.0,
            2914.0,
            2764.0,
            1432.0,
            1228.0,
            785.0,
            2463.0,
            3048.0,
            4325.0,
            2213.0,
            3802.0,
            1876.0,
            693.0,
            1589.0,
            2483.0,
            3767.0,
            797.0,
            4208.0,
            3349.0,
            2496.0,
            481.0,
            1739.0,
            3106.0,
            1528.0,
            4258.0,
            554.0,
            5192.0,
            2602.0,
            4251.0,
            1766.0,
            4690.0,
            4004.0,
            3641.0,
            3724.0,
            2786.0,
            2855.0,
            4067.0,
            1611.0,
            4127.0,
            1142.0,
            2400.0,
            4334.0,
            2119.0,
            446.0,
            4095.0,
            2504.0
          ],
          "down_count": [
            3881.0,
            1678.0,
            3872.0,
            3722.0,
            4117.0,
            2111.0,
            4585.0,
            2041.0,
            3874.0,
            4067.0,
            1513.0,
            1475.0,
            2673.0,
            3732.0,
            3391.0,
            2462.0,
            2639.0,
            4029.0,
            4225.0,
            4674.0,
            2932.0,
            2364.0,
            1145.0,
            3160.0,
            1625.0,
            3534.0,
            4792.0,
            3787.0,
            2885.0,
            1676.0,
            4682.0,
            1247.0,
            2097.0,
            2859.0,
            5000.0,
            3709.0,
            2298.0,
            3875.0,
            1208.0,
            4937.0,
            285.0,
            2768.0,
            1214.0,
            3635.0,
            728.0,
            1465.0,
            1746.0,
            1619.0,
            2590.0,
            2535.0,
            1391.0,
            3776.0,
            1279.0,
            4317.0,
            2969.0,
            1063.0,
            3292.0,
            5068.0,
            1346.0,
            2861.0
          ]
        },
        "labels": {
          "limit_up": "涨停家数",
          "limit_down": "跌停家数",
          "red_ratio": "红盘占比(%)",
          "up_count": "上涨家数",
          "down_count": "下跌家数"
        }
      }
    },
    "similar": {
      "available": true,
      "target_date": "2026-08-21",
      "dims": [
        "up_count",
        "down_count",
        "flat_count",
        "limit_up",
        "limit_down",
        "red_ratio"
      ],
      "dropped": {},
      "n_total": 4771,
      "exclude_window": 15,
      "similar": [
        {
          "date": "2025-04-15",
          "dist": 0.174,
          "fwd": {
            "5": 48.84,
            "10": 68.32,
            "20": 57.93
          }
        },
        {
          "date": "2025-08-08",
          "dist": 0.211,
          "fwd": {
            "5": 87.86,
            "10": 53.92,
            "20": 91.21
          }
        },
        {
          "date": "2025-12-10",
          "dist": 0.237,
          "fwd": {
            "5": 69.02,
            "10": 78.43,
            "20": 74.56
          }
        },
        {
          "date": "2025-10-28",
          "dist": 0.266,
          "fwd": {
            "5": 30.86,
            "10": 52.72,
            "20": 81.25
          }
        },
        {
          "date": "2024-07-02",
          "dist": 0.28,
          "fwd": {
            "5": 82.77,
            "10": 48.54,
            "20": 65.94
          }
        },
        {
          "date": "2025-12-15",
          "dist": 0.326,
          "fwd": {
            "5": 56.83,
            "10": 37.5,
            "20": 51.52
          }
        },
        {
          "date": "2026-04-13",
          "dist": 0.333,
          "fwd": {
            "5": 64.48,
            "10": 61.03,
            "20": 19.25
          }
        },
        {
          "date": "2026-07-16",
          "dist": 0.337,
          "fwd": {
            "5": 77.9,
            "10": 32.7,
            "20": 20.92
          }
        },
        {
          "date": "2025-10-22",
          "dist": 0.366,
          "fwd": {
            "5": 50.51,
            "10": 64.01,
            "20": 22.31
          }
        },
        {
          "date": "2025-07-29",
          "dist": 0.368,
          "fwd": {
            "5": 74.66,
            "10": 39.52,
            "20": 53.11
          }
        },
        {
          "date": "2025-09-17",
          "dist": 0.37,
          "fwd": {
            "5": 83.96,
            "10": 58.95,
            "20": 56.48
          }
        },
        {
          "date": "2025-05-27",
          "dist": 0.381,
          "fwd": {
            "5": 76.26,
            "10": 66.28,
            "20": 75.56
          }
        },
        {
          "date": "2024-03-13",
          "dist": 0.394,
          "fwd": {
            "5": 75.51,
            "10": 11.15,
            "20": 28.92
          }
        },
        {
          "date": "2024-04-02",
          "dist": 0.414,
          "fwd": {
            "5": 52.02,
            "10": 40.75,
            "20": 59.26
          }
        },
        {
          "date": "2025-07-25",
          "dist": 0.417,
          "fwd": {
            "5": 63.5,
            "10": 46.47,
            "20": 53.92
          }
        }
      ],
      "forward_stats": {
        "5": {
          "n": 15,
          "mean": 66.33,
          "median": 69.02,
          "p10": 49.51,
          "p90": 83.48,
          "up_ratio": 86.7
        },
        "10": {
          "n": 15,
          "mean": 50.69,
          "median": 52.72,
          "p10": 34.62,
          "p90": 67.5,
          "up_ratio": 53.3
        },
        "20": {
          "n": 15,
          "mean": 54.14,
          "median": 56.48,
          "p10": 21.48,
          "p90": 78.97,
          "up_ratio": 73.3
        }
      }
    },
    "inflection": {
      "available": true,
      "dims": [
        "up_count",
        "down_count",
        "flat_count",
        "limit_up",
        "limit_down",
        "red_ratio"
      ],
      "dropped": {},
      "events": [
        {
          "dim": "up_count",
          "label": "上涨家数",
          "date": "2026-07-28",
          "type": "触顶回落",
          "extreme": 5192.0,
          "current": 2602.0
        },
        {
          "dim": "down_count",
          "label": "下跌家数",
          "date": "2026-07-28",
          "type": "触底反转",
          "extreme": 285.0,
          "current": 2768.0
        },
        {
          "dim": "red_ratio",
          "label": "红盘占比(%)",
          "date": "2026-07-28",
          "type": "触顶回落",
          "extreme": 94.796,
          "current": 48.454
        },
        {
          "dim": "flat_count",
          "label": "平盘家数",
          "date": "2026-08-10",
          "type": "触顶回落",
          "extreme": 187.0,
          "current": 79.0
        }
      ]
    },
    "duration": {
      "available": true,
      "band_labels": [
        "冰点",
        "偏冷",
        "中性",
        "活跃",
        "狂热"
      ],
      "durations": {
        "0": {
          "n": 571,
          "mean": 1.2,
          "median": 1.0
        },
        "1": {
          "n": 870,
          "mean": 1.3,
          "median": 1.0
        },
        "2": {
          "n": 820,
          "mean": 1.3,
          "median": 1.0
        },
        "3": {
          "n": 805,
          "mean": 1.3,
          "median": 1.0
        },
        "4": {
          "n": 677,
          "mean": 1.3,
          "median": 1.0
        }
      },
      "recovery": {
        "n": 571,
        "mean": 1.3,
        "median": 1.0
      },
      "total_runs": 3743
    }
  }
}

export const breadthZSeries = {
  "dim": "up_count",
  "label": "上涨家数",
  "data_as_of": "2026-08-21",
  "window": 60,
  "available": true,
  "reason": null,
  "dates": [
    "2026-05-29",
    "2026-06-01",
    "2026-06-02",
    "2026-06-03",
    "2026-06-04",
    "2026-06-05",
    "2026-06-08",
    "2026-06-09",
    "2026-06-10",
    "2026-06-11",
    "2026-06-12",
    "2026-06-15",
    "2026-06-16",
    "2026-06-17",
    "2026-06-18",
    "2026-06-22",
    "2026-06-23",
    "2026-06-24",
    "2026-06-25",
    "2026-06-26",
    "2026-06-29",
    "2026-06-30",
    "2026-07-01",
    "2026-07-02",
    "2026-07-03",
    "2026-07-06",
    "2026-07-07",
    "2026-07-08",
    "2026-07-09",
    "2026-07-10",
    "2026-07-13",
    "2026-07-14",
    "2026-07-15",
    "2026-07-16",
    "2026-07-17",
    "2026-07-20",
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
    "2026-07-24",
    "2026-07-27",
    "2026-07-28",
    "2026-07-29",
    "2026-07-30",
    "2026-07-31",
    "2026-08-03",
    "2026-08-04",
    "2026-08-05",
    "2026-08-06",
    "2026-08-07",
    "2026-08-10",
    "2026-08-11",
    "2026-08-12",
    "2026-08-13",
    "2026-08-14",
    "2026-08-17",
    "2026-08-18",
    "2026-08-19",
    "2026-08-20",
    "2026-08-21"
  ],
  "z": [
    -0.72,
    0.9,
    -0.76,
    -0.61,
    -0.85,
    0.58,
    -1.18,
    0.65,
    -0.69,
    -0.83,
    1.08,
    1.03,
    0.16,
    -0.63,
    -0.43,
    0.25,
    0.16,
    -0.93,
    -1.11,
    -1.45,
    0.01,
    0.49,
    1.62,
    -0.26,
    1.13,
    -0.59,
    -1.64,
    -0.82,
    0.06,
    1.25,
    -1.51,
    1.63,
    0.87,
    0.07,
    -1.75,
    -0.59,
    0.67,
    -0.79,
    1.66,
    -1.61,
    2.34,
    0.17,
    1.53,
    -0.54,
    1.89,
    1.31,
    0.99,
    1.03,
    0.27,
    0.3,
    1.26,
    -0.74,
    1.3,
    -1.11,
    -0.12,
    1.45,
    -0.35,
    -1.67,
    1.21,
    -0.06
  ],
  "raw": [
    1536.0,
    3772.0,
    1542.0,
    1712.0,
    1342.0,
    3271.0,
    895.0,
    3319.0,
    1556.0,
    1366.0,
    3919.0,
    3901.0,
    2727.0,
    1720.0,
    2018.0,
    2914.0,
    2764.0,
    1432.0,
    1228.0,
    785.0,
    2463.0,
    3048.0,
    4325.0,
    2213.0,
    3802.0,
    1876.0,
    693.0,
    1589.0,
    2483.0,
    3767.0,
    797.0,
    4208.0,
    3349.0,
    2496.0,
    481.0,
    1739.0,
    3106.0,
    1528.0,
    4258.0,
    554.0,
    5192.0,
    2602.0,
    4251.0,
    1766.0,
    4690.0,
    4004.0,
    3641.0,
    3724.0,
    2786.0,
    2855.0,
    4067.0,
    1611.0,
    4127.0,
    1142.0,
    2400.0,
    4334.0,
    2119.0,
    446.0,
    4095.0,
    2504.0
  ],
  "markers": [
    41
  ],
  "truncated": true,
  "note": "z-score 窗口 60 日；轨迹按 window 截取末段，均为历史形态描述、非预测。"
}


// 演示数据：结构与真端点一致（字段形态来自隔离库真跑/注入，数值为示例）。
export const momentumBreadth = {
  "available": true,
  "reason": null,
  "rr_labels": [
    "冰点",
    "偏冷",
    "中性",
    "活跃",
    "狂热"
  ],
  "mom_labels": [
    "强杀跌≤-1%",
    "-1~0%",
    "0~1%温和",
    "1~2%强",
    "≥2%极强"
  ],
  "matrix": [
    [
      1,
      0,
      0,
      0,
      0
    ],
    [
      0,
      0,
      1,
      2,
      0
    ],
    [
      0,
      1,
      1,
      1,
      1
    ],
    [
      1,
      0,
      0,
      1,
      4
    ],
    [
      0,
      0,
      0,
      0,
      1
    ]
  ],
  "totals_row": [
    1,
    3,
    4,
    6,
    1
  ],
  "totals_col": [
    2,
    1,
    2,
    4,
    6
  ],
  "n_days": 15,
  "current": {
    "available": true,
    "date": "2026-08-21 00:00:00",
    "rr_band": 2,
    "mom_band": 1,
    "rr_label": "中性",
    "mom_label": "-1~0%",
    "red_ratio": 46.67287977632805,
    "zt_prev_ret": -0.6209877983112878
  },
  "stats": {
    "available": true,
    "co_hot": 40.0,
    "co_cold": 13.3,
    "dominant_cell": [
      "活跃",
      "≥2%极强",
      4
    ],
    "n_days": 15
  },
  "trajectory": {
    "available": true,
    "dates": [
      "2026-08-03",
      "2026-08-04",
      "2026-08-05",
      "2026-08-06",
      "2026-08-07",
      "2026-08-10",
      "2026-08-11",
      "2026-08-12",
      "2026-08-13",
      "2026-08-14",
      "2026-08-17",
      "2026-08-18",
      "2026-08-19",
      "2026-08-20",
      "2026-08-21"
    ],
    "rr_band": [
      3,
      3,
      3,
      2,
      2,
      3,
      1,
      3,
      1,
      2,
      4,
      1,
      0,
      3,
      2
    ],
    "mom_band": [
      3,
      4,
      4,
      4,
      3,
      4,
      2,
      4,
      3,
      2,
      4,
      3,
      0,
      0,
      1
    ]
  },
  "note": "共振矩阵为广度（红盘率）× 动量（涨停前日收益代理）的联合分布共现天数，仅描述历史结构，非收益预测。"
}

// 演示数据：结构与真端点一致（字段形态来自隔离库真跑/注入，数值为示例）。
export const limitUpReview = {
  "available": true,
  "date": "20261106",
  "note": "数据源东财涨停池（10 分钟缓存，非实时行情）；龙头评分为启发式加权，不构成投资建议。联网不可用则该页诚实降级。",
  "pool": {
    "available": true,
    "date": "20261106",
    "count": 4,
    "first_boards": 2,
    "connect_boards": 2,
    "max_boards": 3,
    "broken_count": 1,
    "bands": {
      "早板": 1,
      "尾板": 1,
      "上午板": 1,
      "其他": 1
    },
    "rows": [
      {
        "code": "600519",
        "name": "贵州茅台",
        "industry": "白酒",
        "boards": 1,
        "seal": 120000.0,
        "amount": 500000.0,
        "first_seal_band": "早板",
        "broken": 0
      },
      {
        "code": "000001",
        "name": "平安银行",
        "industry": "银行",
        "boards": 2,
        "seal": 80000.0,
        "amount": 300000.0,
        "first_seal_band": "尾板",
        "broken": 1
      },
      {
        "code": "300750",
        "name": "宁德时代",
        "industry": "电池",
        "boards": 3,
        "seal": 200000.0,
        "amount": 900000.0,
        "first_seal_band": "上午板",
        "broken": 0
      },
      {
        "code": "601318",
        "name": "中国平安",
        "industry": "保险",
        "boards": 1,
        "seal": 50000.0,
        "amount": 200000.0,
        "first_seal_band": "其他",
        "broken": 0
      }
    ],
    "leaderboard": [
      {
        "name": "宁德时代",
        "code": "300750",
        "industry": "电池",
        "boards": 3,
        "score": 100.0,
        "s_height": 100.0,
        "s_seal": 100.0,
        "s_ind": 100.0,
        "s_amt": 100.0,
        "ind_n": 1,
        "seal": 200000.0,
        "amount": 900000.0
      },
      {
        "name": "平安银行",
        "code": "000001",
        "industry": "银行",
        "boards": 2,
        "score": 60.0,
        "s_height": 66.7,
        "s_seal": 40.0,
        "s_ind": 100.0,
        "s_amt": 33.3,
        "ind_n": 1,
        "seal": 80000.0,
        "amount": 300000.0
      },
      {
        "name": "贵州茅台",
        "code": "600519",
        "industry": "白酒",
        "boards": 1,
        "score": 57.8,
        "s_height": 33.3,
        "s_seal": 60.0,
        "s_ind": 100.0,
        "s_amt": 55.6,
        "ind_n": 1,
        "seal": 120000.0,
        "amount": 500000.0
      },
      {
        "name": "中国平安",
        "code": "601318",
        "industry": "保险",
        "boards": 1,
        "score": 42.4,
        "s_height": 33.3,
        "s_seal": 25.0,
        "s_ind": 100.0,
        "s_amt": 22.2,
        "ind_n": 1,
        "seal": 50000.0,
        "amount": 200000.0
      }
    ],
    "themes": [
      {
        "industry": "白酒",
        "count": 1
      },
      {
        "industry": "银行",
        "count": 1
      },
      {
        "industry": "电池",
        "count": 1
      },
      {
        "industry": "保险",
        "count": 1
      }
    ],
    "broken_list": [
      {
        "name": "平安银行",
        "code": "000001",
        "boards": 2,
        "broken": 1
      }
    ]
  },
  "ladder": {
    "available": true,
    "distribution": [
      [
        3,
        1
      ],
      [
        2,
        1
      ],
      [
        1,
        2
      ]
    ],
    "max_boards": 3,
    "total_connect": 1,
    "gaps": []
  },
  "context": {
    "available": true,
    "fail_ratio": 18.269230769230766,
    "limit_up_cnt": 85,
    "cycle": "主升高潮",
    "temperature": 87.0,
    "state": "震荡",
    "confidence": 0.6
  }
}

// 演示数据：结构与真端点一致（字段形态来自隔离库真跑/注入，数值为示例）。
export const marketSentiment = {
  "available": true,
  "data_as_of": "2026-03-01",
  "temperature": 45.5,
  "level": {
    "label": "中性",
    "emoji": "⚖️",
    "color": "#2b8aef"
  },
  "dims": {
    "资金": [
      {
        "key": "margin_net",
        "name": "融资净买入额",
        "unit": "亿元",
        "value": 46.79740967869003,
        "spark": [
          43.50043805198705,
          40.2285456286531,
          58.53437652714619,
          44.818303109093335,
          64.9830168306488,
          42.20160635853607,
          53.86501993625832,
          47.72716993442797,
          42.45978190873637,
          55.87675042577753,
          48.450174269251924,
          56.03210580713647,
          49.52708492783004,
          39.14183744698562,
          48.97930756811093,
          50.519551695161404,
          59.584629538811974,
          40.93730992664821,
          49.60670146732694,
          32.781212697699615,
          56.51493060343316,
          39.18517025359354,
          31.936404789163944,
          49.40783165725263,
          61.05684958662846,
          34.75553051788125,
          39.11964414611573,
          42.567251089467184,
          38.70503353657997,
          53.79427888334585,
          41.926325549555145,
          42.78485263539798,
          55.83305398682311,
          42.44485369031316,
          54.32780097780722,
          40.286148281179564,
          37.878614857847104,
          31.645507108090772,
          68.61202786911728,
          46.79740967869003
        ],
        "heat": 53.3,
        "available": true
      },
      {
        "key": "north_net",
        "name": "北向资金净流入",
        "unit": "亿元",
        "value": 43.5270754861272,
        "spark": [
          48.23206806486412,
          38.484808404725285,
          51.16355235692184,
          38.49086478689138,
          61.121072717293,
          60.626506057881556,
          60.84751265296421,
          45.25949529391472,
          55.145205633180886,
          48.67930494780643,
          46.111879385975186,
          46.60854342857934,
          37.002847269658496,
          35.561363041048786,
          57.94314790876046,
          48.0876459608048,
          52.164248511276234,
          60.0171038845412,
          32.66867504983926,
          42.15869926184106,
          51.753348434650704,
          53.92094786665573,
          46.22925549598903,
          60.29179232697849,
          52.10394938829637,
          37.8661786117214,
          40.692362240093544,
          58.05471060494622,
          54.638314564560595,
          31.009387609933988,
          63.477123038624086,
          55.98027031093888,
          63.433429876964986,
          46.16299118924916,
          47.04293778667674,
          38.73542915248681,
          75.36929570131888,
          48.24545774592851,
          65.87533192081946,
          43.5270754861272
        ],
        "heat": 30.0,
        "available": true
      },
      {
        "key": "adl",
        "name": "腾落指数(ADL)",
        "unit": "累积",
        "value": 43.24337748994347,
        "spark": [
          31.582649622082677,
          47.64908868925319,
          37.32553518556297,
          52.71264358821701,
          51.56751086624225,
          48.130690553700454,
          24.83240289179487,
          44.61307104153364,
          49.51499054598928,
          51.133089860033074,
          34.698642344946066,
          45.222467239660695,
          40.214809219433604,
          41.91162760574401,
          60.60898623386079,
          41.92465324668103,
          49.674782950544795,
          58.84389867383174,
          44.16399567256698,
          48.882980504158404,
          51.10464143249481,
          50.63781774255062,
          37.74944173582307,
          50.76140230377008,
          63.588234217415376,
          34.528553218715174,
          58.593826880215985,
          51.19354025696581,
          43.58529605892779,
          70.00416546342423,
          57.62259712084712,
          38.007110978947765,
          50.745162287714635,
          55.76689583670185,
          48.1121787464925,
          56.82910267195206,
          49.334826798505844,
          56.67247560834328,
          64.38522591656152,
          43.24337748994347
        ],
        "heat": 28.3,
        "available": true
      },
      {
        "key": "adr",
        "name": "涨跌比率(ADR)",
        "unit": "比值",
        "value": 51.92745912605072,
        "spark": [
          45.71975057427133,
          46.963196116352705,
          53.525890672852654,
          48.792295549135446,
          48.02715772034277,
          38.85932856848944,
          49.884785319614515,
          45.564187770255806,
          61.66127776190223,
          56.530885027011635,
          49.75856386990068,
          56.68381023267344,
          46.60130448286851,
          60.52126358426947,
          49.94600439328374,
          55.833823541804136,
          37.09106754676513,
          53.4668004887843,
          33.117958826334586,
          29.646710550600677,
          46.95523122288563,
          41.000723924014046,
          51.640527957122224,
          72.4475662648605,
          41.68276818587918,
          43.76056413556094,
          52.05403946064699,
          54.93013291412356,
          48.235939340942416,
          47.940696697467835,
          57.02462955120544,
          55.199076370338986,
          39.66324167926311,
          49.20818681384158,
          50.35286848661474,
          39.4551537795089,
          52.59839100674363,
          41.42043522823456,
          59.720667079170425,
          51.92745912605072
        ],
        "heat": 65.0,
        "available": true
      },
      {
        "key": "nhnl",
        "name": "新高新低指标",
        "unit": "差值",
        "value": 49.66209565232628,
        "spark": [
          60.985867597569175,
          44.57108068269813,
          49.48809587308323,
          42.06703596796957,
          43.739269002798025,
          37.222748483488296,
          62.57069313714393,
          48.45912426793987,
          59.65921618728809,
          50.133245969132595,
          43.055964722971055,
          46.733147399977476,
          44.397689494971004,
          50.07959099184914,
          46.24733160323044,
          47.00078284058202,
          36.214253158640865,
          41.93154072378879,
          66.5405754880043,
          43.28766783748283,
          39.45906212376507,
          53.37326332575031,
          64.07272199556532,
          35.459756975187915,
          47.91478151748729,
          43.67947446065092,
          32.38980525672597,
          57.349267092583915,
          49.765560814451554,
          50.71441844292605,
          42.476885275544106,
          54.54784162996916,
          44.60702650512679,
          48.57096791503239,
          38.91739207818487,
          37.83897239791805,
          63.355318553000224,
          44.92895295461525,
          52.91680356355802,
          49.66209565232628
        ],
        "heat": 63.3,
        "available": true
      }
    ],
    "情绪": [
      {
        "key": "vix",
        "name": "VIX恐慌指数",
        "unit": "指数",
        "value": 35.50136178093389,
        "spark": [
          37.534069417142916,
          58.61723076993649,
          54.93932079030758,
          58.73619113524502,
          68.79008307096737,
          64.84445473378649,
          38.54823092810675,
          33.113284197321434,
          58.16889059053797,
          39.849875841240774,
          49.87594611352487,
          58.397274770051936,
          33.56202648814414,
          28.900195456905212,
          52.59299020337227,
          50.44385889613297,
          47.54196928618077,
          50.38534763770218,
          41.394843926327205,
          34.86505592727893,
          48.33345149119678,
          40.28291308950608,
          33.56518677588893,
          55.05681071393277,
          49.38601371577824,
          54.06528536632814,
          40.10705058574063,
          43.419412081633425,
          40.00956972779834,
          41.13358132941952,
          51.95407917749402,
          42.170253836650545,
          53.56066288820274,
          53.39755925418216,
          70.25160986880103,
          36.072109541331905,
          58.87902377835046,
          49.10512038111582,
          49.85970269869003,
          35.50136178093389
        ],
        "heat": 90.0,
        "available": true
      },
      {
        "key": "pcr",
        "name": "PCR(认沽/认购比)",
        "unit": "比值",
        "value": 50.54303611713694,
        "spark": [
          50.38400261555346,
          58.05405646943798,
          55.52567297356075,
          52.157047000244944,
          39.57131642409989,
          55.11108764909727,
          43.15752922007506,
          60.93845675900479,
          37.289491782758724,
          48.623790237244116,
          49.92641713708729,
          36.753544493558636,
          67.21971643856479,
          64.60406767259552,
          45.36416238390917,
          57.71721165564523,
          53.78676069670212,
          23.86440536654742,
          52.5039801627759,
          49.38655920166752,
          50.8321735347453,
          39.231250801728216,
          47.30652953779595,
          48.21741236617703,
          61.880942172123184,
          53.34427060391015,
          49.94444969797336,
          65.2896999791094,
          44.447520702363526,
          46.10569695124615,
          31.832449886609403,
          65.69105846283612,
          59.64332368194428,
          59.168480445117076,
          56.68898446446937,
          51.10148587663652,
          52.15488939182329,
          47.47993409732692,
          47.963995742770535,
          50.54303611713694
        ],
        "heat": 43.3,
        "available": true
      },
      {
        "key": "zt_ratio",
        "name": "涨停家数占比",
        "unit": "%",
        "value": 49.16030296466824,
        "spark": [
          42.294013234351404,
          55.77046747300695,
          65.2443745272676,
          46.86403738718374,
          43.98423747876534,
          51.91432259126093,
          49.979709723909714,
          40.063836526602884,
          54.60919415713379,
          70.15516053475409,
          47.41888004734276,
          47.971238039353366,
          39.550679764309145,
          53.190884516865474,
          37.53023775292372,
          38.930689756485165,
          62.7966727184379,
          40.94546940605356,
          60.81357569331338,
          65.24358003782807,
          52.59326457476743,
          55.533914028508235,
          69.52250943686778,
          48.03271597934283,
          44.069942030583846,
          36.46768935217058,
          50.41707080346346,
          64.79144210918307,
          59.59595381400865,
          40.579087585820425,
          41.44624616167404,
          44.95828770659036,
          52.92268082495342,
          47.94688572896316,
          52.14453945443081,
          52.96739378045447,
          47.012264133215524,
          49.598260583970564,
          52.06592377216034,
          49.16030296466824
        ],
        "heat": 48.3,
        "available": true
      }
    ],
    "估值": [
      {
        "key": "pe_pct",
        "name": "PE历史百分位",
        "unit": "%",
        "value": 29.24726722088689,
        "spark": [
          47.14584172784159,
          34.937208993604365,
          40.22742149501903,
          63.858391630461185,
          58.20578685890059,
          45.983318478493246,
          41.29827629795744,
          31.06192863488186,
          46.063432880990156,
          49.69096747413702,
          49.15945642165516,
          49.0620807202383,
          38.781903727730736,
          49.33726114634382,
          49.61326620464894,
          62.90562037803177,
          68.66733454352362,
          48.630109730822085,
          42.33694048824113,
          49.35017870238036,
          43.92378724745563,
          42.57566184253751,
          49.41349848077858,
          39.56695568847685,
          56.06106751155018,
          48.96084450815923,
          52.50008306859952,
          48.17059964029328,
          42.727455527475875,
          40.52040440251148,
          47.62723995675459,
          44.51239662572188,
          52.33901333209575,
          49.95568296802361,
          36.376932520772705,
          50.671212994283515,
          36.57139582859243,
          43.835223744807195,
          47.056463907821524,
          29.24726722088689
        ],
        "heat": 3.3,
        "available": true
      },
      {
        "key": "div_yield",
        "name": "股息率",
        "unit": "%",
        "value": 39.97404803615891,
        "spark": [
          43.46355593407149,
          47.405399416985645,
          56.37058331216349,
          54.306392440831104,
          52.067127654426486,
          34.856797548803726,
          55.37887114883208,
          61.694709919931064,
          60.096714930428575,
          52.338780487691054,
          34.423213963958055,
          59.4254481422802,
          48.52745363280233,
          24.674803519330343,
          53.77207403107204,
          35.078282169204634,
          37.03559419804937,
          43.65041107626147,
          62.72591177882884,
          46.29154645821607,
          52.70991587736716,
          67.47967963752231,
          65.94029762655792,
          48.96646584172635,
          47.58478977939489,
          37.3912936591045,
          43.05541925818409,
          54.2535834761277,
          53.957307618096465,
          51.102382311739596,
          59.94801657563926,
          42.27631986966819,
          49.43923479816535,
          57.31242988494812,
          55.84145906227918,
          60.709457757324195,
          53.970204067650606,
          46.905974444031685,
          53.621922602624,
          39.97404803615891
        ],
        "heat": 85.0,
        "available": true
      }
    ],
    "宏观": [
      {
        "key": "m2_yoy",
        "name": "M2同比增速",
        "unit": "%",
        "value": 46.48722311812633,
        "spark": [
          61.350456790964806,
          53.125628347462474,
          53.019760061154265,
          57.869453479945996,
          44.606730052576594,
          49.59811945056815,
          59.062390030785366,
          69.57445214895091,
          48.40732694268258,
          49.51599310670136,
          51.98480193787679,
          63.432036940080565,
          49.696866964108494,
          64.69359036471145,
          40.33342782571249,
          48.13963704263005,
          48.01834843314474,
          57.8650572409622,
          60.45260376978278,
          34.905556418817675,
          40.848823741887756,
          53.36852478776462,
          43.41306354114185,
          34.775722243523575,
          60.384799720234795,
          54.939700841536485,
          54.93177496860747,
          45.24554283553905,
          60.28938452167321,
          47.600400035728796,
          60.964352778229525,
          40.88334849057378,
          41.45864552316199,
          52.04663210597696,
          42.97667854202941,
          56.7545106536883,
          52.600877441290535,
          40.77028782136902,
          50.728656009451,
          46.48722311812633
        ],
        "heat": 33.3,
        "available": true
      },
      {
        "key": "pmi",
        "name": "PMI(采购经理指数)",
        "unit": "指数",
        "value": 46.69805907275661,
        "spark": [
          56.1914087909471,
          46.65097201286526,
          54.987157004806015,
          41.09939707879157,
          46.38285974321988,
          39.75584412212129,
          61.317672163619164,
          49.729167719330086,
          42.606925123697,
          46.47628201934853,
          47.78271519276725,
          57.00519791325009,
          34.04363821814764,
          39.62794158374581,
          46.21892748442503,
          75.32305832767807,
          59.55678892531995,
          48.885483208690566,
          57.11999582410839,
          70.57436169630336,
          47.6625607322461,
          46.335866559024396,
          62.11943543221896,
          54.941754981329424,
          56.713331553225565,
          44.91777600719419,
          69.24203132342743,
          67.0959080159366,
          55.6594778887275,
          56.842898381472374,
          29.727391277569645,
          56.377097934972085,
          48.05891412774677,
          54.33905705828222,
          56.82459411846098,
          46.58708231891725,
          33.095181998129156,
          53.67874565074235,
          42.58616347559605,
          46.69805907275661
        ],
        "heat": 38.3,
        "available": true
      }
    ],
    "技术": [
      {
        "key": "idx_ma5",
        "name": "MA5",
        "unit": "点位",
        "value": 28.9955975966264,
        "spark": [
          56.96922803119213,
          48.88573431293293,
          53.56837278352538,
          51.05721544699983,
          56.31654734148375,
          50.380187470155356,
          62.36202483478212,
          54.24982789977226,
          53.92067623388404,
          54.09866917682557,
          35.4336225743128,
          48.3536424819628,
          47.40683510450502,
          52.075467211604845,
          36.41305835703708,
          66.3411477689291,
          51.04388664156527,
          37.88682459349326,
          32.91113036421162,
          47.187127062793316,
          49.10324587073534,
          42.817079140256105,
          50.92113827923923,
          43.58824232760439,
          55.516582517062986,
          42.75458181611116,
          49.61499774895075,
          59.78839173362138,
          75.71668882910294,
          39.923568073693936,
          45.35492229912901,
          41.60164302200066,
          57.84328321769275,
          38.51900694282437,
          45.156429544069134,
          49.703987167624895,
          40.21321460520256,
          40.426749576908186,
          45.24377111878135,
          28.9955975966264
        ],
        "heat": null,
        "available": true
      },
      {
        "key": "rsi",
        "name": "RSI",
        "unit": "0-100",
        "value": 34.259671576626744,
        "spark": [
          44.60221984268308,
          43.875285565958265,
          33.17243609131113,
          49.70372685150671,
          68.45533710623317,
          69.80495062884604,
          63.218175965449426,
          57.05801600851558,
          43.23519875920012,
          64.42750788216262,
          49.43872445559031,
          49.31124490236927,
          47.08772868160735,
          50.919618990182954,
          45.64785098411944,
          49.162178306268935,
          39.154008912727384,
          46.26336295259482,
          72.80556469949822,
          49.30405972038053,
          47.61339435228237,
          55.32374279105053,
          57.08121821703462,
          38.86231140827927,
          47.92841217196755,
          59.182758409347656,
          52.69837629072106,
          51.21954043501772,
          65.54017668608734,
          43.22227240360356,
          50.82745895107633,
          44.79941334744929,
          64.90308229076241,
          30.48139600723468,
          43.2985830451624,
          44.70843033972082,
          56.6353962317159,
          56.06275476109527,
          63.95194260238732,
          34.259671576626744
        ],
        "heat": 10.0,
        "available": true
      }
    ]
  },
  "unavailable": [],
  "note": "综合市场温度由可用指标近期分位多空加权得出（高=热：ADR/涨停/PE/北向/融资净买；高=冷：VIX/PCR/股息率）。温度计为风险/健康语义，与价格涨跌红绿无关。"
}

// ───────── 星辰 AI（53 页 v2 /xingchen）开发期样例 ─────────
// ⚠️ 演示数据：ai_consult 任务结果仅含 {answer, independent, specialist?}（与后端 ai_answer 真实返回一致）；
// 数值与 [S#] 引用为示例、非真实行情/真实来源。Answer 含 [S#] 引用徽标，供前端引用徽标渲染测试。
export const chatSampleResult = {
  answer:
    '**贵州茅台（600519）· 综合评分 60 分 · 中性偏多**\n\n' +
    '### 技术面\n' +
    '- 当前价 1523.5，站上 MA20（1476），RSI 63 未超买；量比 0.9 缩量整理。\n' +
    '- 关键点位：支撑 1490，压力 1540[S1]。\n\n' +
    '### 基本面\n' +
    '- 2025 三季营收 1231 亿（同比 +12.3%），ROE 24.3%，毛利率 91.2%，现金奶牛属性不变[S2]。\n' +
    '- 估值 PE-TTM 28.1，处历史 30% 分位，不贵。\n\n' +
    '### 结论\n' +
    '短中期中性偏多，回踩 1490 不破可关注；上方 1540 为筹码密集区。\n' +
    '> 以上为规则引擎基于离线数据的结构化研判，不构成投资建议。',
  independent: true,
}

// 命中多 Agent 专家分工时的样例（specialist 字段存在，供前端 specialist 渲染分支测试）
export const chatSampleResultSpecialist = {
  ...chatSampleResult,
  specialist: 'technical_analyst',
}

// 初始会话列表（GET /api/chat/conversations 的演示数据）
export const chatConversations = [
  { id: 1, title: '贵州茅台 研判', updated_at: '2026-11-13T10:00:00Z', message_count: 2 },
]

// 会话消息（GET /api/chat/conversations/<id> 的演示数据；落库仅 user/assistant）
export const chatMessages: Record<number, Array<{ role: string; content: string; ts?: number; chips?: string[] }>> = {
  1: [
    { role: 'user', content: '分析一下贵州茅台', ts: 1763023200 },
    { role: 'assistant', content: chatSampleResult.answer, ts: 1763023260 },
  ],
}

// 旧单记录模式兜底（GET /api/chat/history，供 404 回退路径测试）
export const chatHistory = [
  { role: 'user', content: '分析一下贵州茅台', ts: 1763023200 },
  { role: 'assistant', content: chatSampleResult.answer, ts: 1763023260 },
]
