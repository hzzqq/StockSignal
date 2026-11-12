import { describe, it, expect } from 'vitest'
import {
  parseKlineRows,
  intradayLabel,
  rollingMean,
  emaSeries,
  macdSeries,
  intradayAvg,
  type IntradayPoint,
} from './klineMath'

/** 构造分时点（默认字段齐全）。 */
function pt(amount: number | null, volume: number | null, close: number | null = 10): IntradayPoint {
  return { time: '2026-11-06 09:30:00', label: '09:30', close, volume, amount }
}

describe('intradayAvg · 累计均价（累计成交额 / 累计成交量）诚实口径', () => {
  it('标准累计：金额与成交量成对累加 → [10, 10.67]', () => {
    const out = intradayAvg([pt(1000, 100), pt(600, 50)])
    expect(out[0]).toBe(10)
    expect(out[1]).toBeCloseTo(1600 / 150, 6)
  })

  it('⚠️ amount 单点缺失 → 缺失点显 null，累计口径不得被「分子没加、分母照加」稀释', () => {
    const out = intradayAvg([
      pt(1000, 100), // 累计 (1000, 100) → 10
      pt(null, 50),  // amount 缺失、volume 有效：不得把 50 加进分母
      pt(600, 50),   // 累计应仍为 (1600, 150) → 10.67
    ])
    expect(out[0]).toBe(10)
    expect(out[1]).toBeNull()
    expect(out[2]).toBeCloseTo(1600 / 150, 6)
  })

  it('⚠️ volume 单点缺失 → 同样成对处理，不得把 amount 单加进分子', () => {
    const out = intradayAvg([
      pt(1000, 100),
      pt(600, null), // volume 缺失
      pt(600, 50),
    ])
    expect(out[0]).toBe(10)
    expect(out[1]).toBeNull()
    expect(out[2]).toBeCloseTo(1600 / 150, 6)
  })

  it('全缺失 → 全 null，绝不补 0、不拿收盘价冒充均价', () => {
    const out = intradayAvg([pt(null, null), pt(null, null)])
    expect(out).toEqual([null, null])
  })

  it('累计成交量为 0 → null；单点零成交且累计已有效 → 保持上一均价（不编造）', () => {
    expect(intradayAvg([pt(0, 0)])).toEqual([null])
    expect(intradayAvg([pt(1000, 100), pt(0, 0)])).toEqual([10, 10])
  })
})

describe('rollingMean / emaSeries · 样本不足与缺口一律 null，不补 0', () => {
  it('rollingMean：前 window-1 根 null；窗口内任一缺失 → 该点 null', () => {
    expect(rollingMean([1, 2, 3, 4], 3)).toEqual([null, null, 2, 3])
    expect(rollingMean([1, null, 3, 4], 2)).toEqual([null, null, null, 3.5])
  })

  it('rollingMean：window<=0 → 全 null', () => {
    expect(rollingMean([1, 2], 0)).toEqual([null, null])
  })

  it('emaSeries：前 period-1 根 null，首值取前 period 个样本的 SMA，其后按 EMA 递推', () => {
    // period=3 → k=2/(3+1)=0.5；首值 (1+2+3)/3=2，其后 4*0.5+2*0.5=3，5*0.5+3*0.5=4
    expect(emaSeries([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4])
  })

  it('emaSeries：序列中遇 null 断链，需重新攒够 period 个连续样本才出值', () => {
    expect(emaSeries([1, 2, 3, null, 4, 5, 6], 3)).toEqual([
      null, null, 2, null, null, null, 5,
    ])
  })
})

describe('macdSeries · 未就绪段一律 null，绝不补 0', () => {
  it('slow=26 未就绪前 DIF 全 null；DEA/HIST 需再攒 signal=9 个连续 DIF', () => {
    const closes = Array.from({ length: 45 }, (_, i) => 100 + i)
    const m = macdSeries(closes)
    expect(m.dif.slice(0, 25).every((v) => v === null)).toBe(true)
    expect(m.dif[25]).not.toBeNull()
    // dif 从 index 25 起连续，emaSeries(dif, 9) 首个值落在 25+9-1=33
    expect(m.dea.slice(0, 33).every((v) => v === null)).toBe(true)
    expect(m.hist.slice(0, 33).every((v) => v === null)).toBe(true)
    expect(m.hist[33]).not.toBeNull()
    expect(m.hist.every((v) => v === null || Number.isFinite(v))).toBe(true)
  })
})

describe('parseKlineRows / intradayLabel · 缺失不补零', () => {
  it('date 缺失行丢弃；NaN / Infinity / 字符串数值一律洗成 null', () => {
    const bars = parseKlineRows([
      { date: '2026-01-01', open: 10, high: NaN, low: Infinity, close: 11, volume: 100 },
      { open: 10 }, // 无 date → 丢弃
      { date: '2026-01-02', open: '12', close: null, volume: 0 },
    ])
    expect(bars).toHaveLength(2)
    expect(bars[0].high).toBeNull()
    expect(bars[0].low).toBeNull()
    expect(bars[0].close).toBe(11)
    expect(bars[1].open).toBeNull() // 字符串不冒充数值
    expect(bars[1].close).toBeNull()
    expect(bars[1].volume).toBe(0) // 真 0 保留
  })

  it('intradayLabel：带日期 / 纯时刻 / 无法解析', () => {
    expect(intradayLabel('2026-11-06 09:30:00')).toBe('09:30')
    expect(intradayLabel('09:30')).toBe('09:30')
    expect(intradayLabel('n/a')).toBe('n/a')
  })
})
