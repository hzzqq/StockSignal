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
