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
