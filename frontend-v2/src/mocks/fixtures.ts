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
