import { describe, it, expect } from 'vitest'
import { classifyIntent, extractTopic } from './intent'

describe('classifyIntent（规则引擎）', () => {
  it('研判类：带代码 → analyze + 追问 chips', () => {
    const r = classifyIntent('茅台 600519 怎么样？')
    expect(r.kind).toBe('analyze')
    expect(r.needsParam).toBe(false)
    expect(r.suggestionChips.length).toBeGreaterThan(0)
  })

  it('对比类：含「对比」→ compare', () => {
    expect(classifyIntent('宁德时代和比亚迪对比').kind).toBe('compare')
  })

  it('解释类：含「为什么」→ explain', () => {
    expect(classifyIntent('为什么今天大跌？').kind).toBe('explain')
  })

  it('多空类：含「看多」→ debate', () => {
    expect(classifyIntent('新能源后市看多还是看空？').kind).toBe('debate')
  })

  it('数据类：含「估值」→ data', () => {
    expect(classifyIntent('茅台的估值和毛利率如何？').kind).toBe('data')
  })

  it('缺分析标的 → needsParam 为真，并给出追问项', () => {
    const r = classifyIntent('你好')
    expect(r.needsParam).toBe(true)
    expect(r.paramPrompts.length).toBeGreaterThan(0)
    expect(r.suggestionChips).toHaveLength(0)
  })

  it('纯泛泛提问且无标的 → general，置信压低', () => {
    const r = classifyIntent('随便聊聊')
    expect(r.kind).toBe('general')
    expect(r.confidence).toBeLessThan(0.6)
  })

  // 诚实红线回归：中文股票名/实体不得被前端误拦截，须放行给后端兜底
  it.each(['通富微电之后怎么走', '通富微电怎么看'])(
    '中文股票名提问「%s」→ needsParam=false（放行给后端解析/兜底）',
    (q) => {
      const r = classifyIntent(q)
      expect(r.needsParam).toBe(false)
      expect(r.paramPrompts).toHaveLength(0)
      // 放行后仍保留追问 chips（后端兜底或回答完可继续聊）
      expect(r.suggestionChips.length).toBeGreaterThan(0)
    },
  )

  it('含中文实义串但不在硬编码词表 → 也不误拦截', () => {
    expect(classifyIntent('寒武纪还能追吗').needsParam).toBe(false)
    expect(classifyIntent('为什么大涨').needsParam).toBe(false)
  })

  it('纯语气词仍追问（保留 ParamPromptCard 功能，不删功能）', () => {
    for (const q of ['嗯', '哦哦', 'ok', '在吗']) {
      const r = classifyIntent(q)
      expect(r.needsParam).toBe(true)
      expect(r.paramPrompts.length).toBeGreaterThan(0)
    }
  })
})

describe('extractTopic（诚实抽取：宁可抽不出也不误抽）', () => {
  it('6 位代码优先', () => {
    expect(extractTopic('600519 现在能买吗')).toBe('600519')
  })

  it('中文股票名：「通富微电」两问句均抽出实体', () => {
    expect(extractTopic('通富微电之后怎么走')).toBe('通富微电')
    expect(extractTopic('通富微电怎么看')).toBe('通富微电')
  })

  it('后缀白名单命中：歌尔股份值得买吗 → 歌尔股份', () => {
    expect(extractTopic('歌尔股份值得买吗')).toBe('歌尔股份')
  })

  it('纯寒暄不抽实体', () => {
    expect(extractTopic('你好')).toBeUndefined()
    expect(extractTopic('谢谢')).toBeUndefined()
  })

  it('泛泛提问不误抽伪实体', () => {
    // 「大盘」是既有 ENTITY_KEYWORDS 的语义正确命中；守卫点是绝不误抽「今天大盘」这类句子片段
    expect(extractTopic('今天大盘怎么样')).toBe('大盘')
    expect(extractTopic('今天大盘怎么样')).not.toBe('今天大盘')
    expect(extractTopic('随便聊聊')).toBeUndefined()
    expect(extractTopic('怎么充电比较快')).toBeUndefined()
  })

  it('不在词表/后缀覆盖的名字宁可放弃，不硬抽（中际旭创 → undefined）', () => {
    expect(extractTopic('今天能买中际旭创吗')).toBeUndefined()
  })
})
