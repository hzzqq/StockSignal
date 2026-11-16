import { z } from 'zod'
import { MOCK_WRITE_TS } from './writeEnvelope'
import {
  PriceAlertSchema,
  PriceAlertListSchema,
  MarketAlertSchema,
  MarketAlertListSchema,
  AlertConfigSchema,
  MarketAlertConfigGetSchema,
  ScanResultSchema,
  CreatePriceAlertInputSchema,
  type PriceAlert,
  type MarketAlert,
} from '@/api/schemas/alertWrite'

/**
 * 价格预警 / 市场告警 演示夹具（形状与真后端一致，数值为演示）。
 *
 * 诚实要点：
 *  - 四类 alert_type 各一条；非 price 类型 target_price 为 0.0（后端默认值，非伪造行情）；
 *  - params 是 JSON 文本字符串（后端 Text 列原样返回），price 类型 params 为 null；
 *  - 市场告警 severity 三档齐全，并含 value:null / threshold:null 的诚实空值样本；
 *  - created_at 全部用固定 ISO 戳，禁止 new Date() 冒充数据日。
 */

const T1 = '2026-01-01T08:00:00Z'
const T2 = '2026-01-01T09:00:00Z'
const T3 = '2026-01-01T10:00:00Z'
const T4 = '2026-01-01T11:00:00Z'

/** 四类预警各一条（price 目标价 / pattern 形态 / volume 量比 / announcement 关键词）。 */
export const initialPriceAlerts: PriceAlert[] = [
  {
    id: 1,
    user_id: 1,
    stock_code: '600519',
    stock_name: '贵州茅台',
    alert_type: 'price',
    condition: 'above',
    target_price: 1850.5,
    params: null,
    active: true,
    triggered: false,
    triggered_at: null,
    created_at: MOCK_WRITE_TS,
  },
  {
    id: 2,
    user_id: 1,
    stock_code: '000001',
    stock_name: '平安银行',
    alert_type: 'pattern',
    condition: 'above',
    target_price: 0,
    params: JSON.stringify({ pattern_name: '早晨之星' }),
    active: true,
    triggered: false,
    triggered_at: null,
    created_at: MOCK_WRITE_TS,
  },
  {
    id: 3,
    user_id: 1,
    stock_code: '300750',
    stock_name: '宁德时代',
    alert_type: 'volume',
    condition: 'above',
    target_price: 0,
    params: JSON.stringify({ volume_ratio: 2.5 }),
    active: false,
    triggered: true,
    triggered_at: T2,
    created_at: MOCK_WRITE_TS,
  },
  {
    id: 4,
    user_id: 1,
    stock_code: '002594',
    stock_name: '比亚迪',
    alert_type: 'announcement',
    condition: 'above',
    target_price: 0,
    params: JSON.stringify({ keyword: '减持' }),
    active: true,
    triggered: false,
    triggered_at: null,
    created_at: MOCK_WRITE_TS,
  },
]

/** severity 三档 + value:null / threshold:null 的诚实空值样本。 */
export const initialMarketAlerts: MarketAlert[] = [
  {
    id: 1,
    metric_key: 'adr',
    metric_name: '涨跌家数比',
    severity: 'info',
    message: '涨跌家数比回升至 1.2，市场广度转暖（演示）',
    value: 1.2,
    threshold: 1.0,
    created_at: T1,
  },
  {
    id: 2,
    metric_key: 'vix',
    metric_name: '波动率指数',
    severity: 'warning',
    message: '波动率指数升至 22.5，超过预警阈值（演示）',
    value: 22.5,
    threshold: 20,
    created_at: T2,
  },
  {
    id: 3,
    metric_key: 'pcr',
    metric_name: 'Put/Call 比率',
    severity: 'danger',
    message: '期权 Put/Call 比率取不到实时值，仅记录阈值触发（演示）',
    value: null,
    threshold: 1.5,
    created_at: T3,
  },
  {
    id: 4,
    metric_key: 'adl',
    metric_name: '腾落指数',
    severity: 'info',
    message: '腾落指数走弱，暂无固定阈值（演示）',
    value: -120,
    threshold: null,
    created_at: T4,
  },
]

export const initialConfig: Record<string, unknown> = {
  adr_warning: 1.5,
  vix_danger: 30,
  lookback_days: 5,
  enabled: true,
}

export const initialRuntimeOverrides: Record<string, unknown> = {
  vix_danger: 32,
}

/** 四类创建入参样本（discriminatedUnion 每支一条，用于契约自洽校验）。 */
const createInputSamples: unknown[] = [
  { stock_code: '600519', stock_name: '贵州茅台', alert_type: 'price', condition: 'above', target_price: 1850.5 },
  { stock_code: '000001', alert_type: 'pattern', params: { pattern_name: '早晨之星' } },
  { stock_code: '300750', alert_type: 'volume', params: { volume_ratio: 2.5 } },
  { stock_code: '002594', alert_type: 'announcement', params: { keyword: '减持' } },
]

const marketAlertListSample = {
  items: initialMarketAlerts,
  unread_count: initialMarketAlerts.length,
  total: initialMarketAlerts.length,
  last_seen: null,
}

/**
 * 供契约漂移守卫消费：每个 sample 必须能被对应 schema 严格 parse。
 * 形状与 tests/unit/contract-drift.test.ts::Pair 一致（由 team-lead 统一接线）。
 */
export const alertWriteFixturePairs: Array<{ name: string; schema: z.ZodTypeAny; samples: unknown[] }> = [
  { name: 'price-alert', schema: PriceAlertSchema, samples: initialPriceAlerts },
  { name: 'price-alert-list', schema: PriceAlertListSchema, samples: [initialPriceAlerts] },
  { name: 'create-price-alert-input', schema: CreatePriceAlertInputSchema, samples: createInputSamples },
  { name: 'market-alert', schema: MarketAlertSchema, samples: initialMarketAlerts },
  { name: 'market-alert-list', schema: MarketAlertListSchema, samples: [marketAlertListSample] },
  { name: 'alert-config', schema: AlertConfigSchema, samples: [{ config: initialConfig }] },
  {
    name: 'market-alert-config-get',
    schema: MarketAlertConfigGetSchema,
    samples: [{ config: initialConfig, runtime_overrides: initialRuntimeOverrides }],
  },
  { name: 'scan-result', schema: ScanResultSchema, samples: [{ inserted: 2 }] },
]
