/**
 * 星辰 AI · 客户端意图分类（规则引擎，零 LLM 成本）。
 *
 * 镜像 v1 `pages/53_星辰AI.py` 的 `_xc_suggestion_kind` + FinPilot `classifyIntent`：
 * 提交瞬间先用关键词规则判定问题类型、生成「问题分析卡」步骤（ProcessCard 数据源）
 * 与追问 chips；若缺少分析标的则标记 needsParam（→ ParamPromptCard 缺参追问）。
 *
 * 诚实红线：纯规则、确定性输出、不调用任何模型；命中不到就标 general，绝不编造高置信度。
 */

export type XcStyle = 'quick' | 'report' | 'debate' | 'teach'

export type XcIntentKind =
  | 'analyze'
  | 'compare'
  | 'explain'
  | 'debate'
  | 'data'
  | 'general'

export interface XcIntent {
  kind: XcIntentKind
  label: string
  confidence: number
  /** 问题分析卡步骤（ProcessCard 渲染，planner→analysis→debate 顺序） */
  processSteps: string[]
  /** assistant 轮末尾的追问 chips（点击直接发送） */
  suggestionChips: string[]
  /** 是否缺分析标的（→ ParamPromptCard 缺参追问） */
  needsParam: boolean
  paramPrompts: string[]
}

const ENTITY_KEYWORDS = [
  '股票', '个股', '指数', '板块', '大盘', '基金', 'ETF', '标的', '行情', '市场',
  'A股', '行业', '公司', '企业', '龙头', '茅台', '宁德', '比亚迪', '贵州', '腾讯',
  '阿里', '苹果', '英伟达', '半导体', '新能源', '医药', '银行', '券商', '地产',
  '白酒', '汽车', '军工', '消费', '科技', '光伏', '锂电', '化工', '钢铁', '煤炭',
  '保险', '电力', '农业', '物流', '通信', '传媒', '游戏', '软件', '芯片', '算力',
]

const KIND_LABELS: Record<XcIntentKind, string> = {
  analyze: '个股/标的研判',
  compare: '标的对比',
  explain: '概念/逻辑解释',
  debate: '多空辩论',
  data: '数据/财务拆解',
  general: '通用问答',
}

/** 回应风格文案（对标 FinPilot「深度研究」等标题）。 */
export const STYLE_LABELS: Record<XcStyle, string> = {
  quick: '快速研判',
  report: '深度研究',
  debate: '多空辩论',
  teach: '教学讲解',
}

/**
 * 研判维度框架（对标 FinPilot 8 模块卡网格）。
 * 诚实红线：这是客户端分析透镜（按意图套用的研究框架），不是从后端拆出的独立数据，
 * 故卡片只标「分析中/已返回」状态，绝不编造假数值。
 */
export const DIMENSIONS: Record<XcIntentKind, { label: string; desc: string }[]> = {
  analyze: [
    { label: '基本面', desc: '业绩 / 估值 / 护城河' },
    { label: '技术面', desc: '趋势 / 量价 / 形态' },
    { label: '资金面', desc: '主力 / 北向 / 流入' },
    { label: '情绪面', desc: '热度 / 恐慌贪婪' },
    { label: '估值', desc: 'PE/PB/分位' },
    { label: '风险', desc: '下行 / 黑天鹅' },
  ],
  compare: [
    { label: '走势对比', desc: '区间涨跌幅' },
    { label: '估值对比', desc: 'PE/PB 分位' },
    { label: '资金对比', desc: '主力净流入' },
    { label: '基本面', desc: '盈利质量' },
    { label: '风险对比', desc: '波动 / 回撤' },
  ],
  explain: [
    { label: '概念界定', desc: '边界 / 定义' },
    { label: '因果链条', desc: '驱动变量' },
    { label: '关键变量', desc: '敏感因子' },
    { label: '通俗重构', desc: '小白能懂' },
  ],
  debate: [
    { label: '看多方', desc: '逻辑 + 举证' },
    { label: '看空方', desc: '风险 + 反驳' },
    { label: '论据权重', desc: '确定性评估' },
    { label: '平衡结论', desc: '概率偏向' },
  ],
  data: [
    { label: '字段定位', desc: '所需财务/行情' },
    { label: '时效校验', desc: '口径 / 日期' },
    { label: '比率计算', desc: '关键指标' },
    { label: '数值结论', desc: '量化输出' },
  ],
  general: [
    { label: '意图解析', desc: '问题拆解' },
    { label: '知识检索', desc: '相关规则/数据' },
    { label: '结构组织', desc: '结构化回答' },
  ],
}

/**
 * 从问题抽取标的主题：6 位代码 → 实体关键词 → 中文公司名候选（保守启发式）。
 * 命中不到返回 undefined（诚实不编造，宁可抽不出也不误抽）。
 */
export function extractTopic(question: string): string | undefined {
  const q = (question || '').trim()
  const code = q.match(/\b\d{6}\b/)
  if (code) return code[0]
  for (const k of ENTITY_KEYWORDS) {
    if (q.includes(k)) return k
  }
  return extractChineseName(q)
}

/** 连续中文串（候选实体切分单元）。 */
const HAN_RUN_RE = /[\u4e00-\u9fff]+/g

/** 候选实体首部需剥掉的口水/称谓/时地域动词前缀（迭代剥到稳定）。 */
const LEADING_FILLER_RE =
  /^(?:请问|您看|你觉得|你想|我想|我想知道|我想了解|帮我|帮忙|帮忙看看|看看|说说|谈谈|讲讲|聊聊|分析一下|分析下|分析|评估|研判|解读|介绍一下|介绍下|查一下|查下|现在|目前|最近|今天|明天|当前|这个|那个|再|又|也|都|就|买|卖|加仓|减仓|建仓|上车)+/

/** 候选实体尾部需剥掉的连接词/疑问/动宾后缀（迭代剥到稳定；长词在前防吞半截）。 */
const TRAILING_FILLER_RE =
  /(?:之后|以后|然后|接下来|怎么样|怎么看|怎么走|怎么办|如何看待|如何|走势|前景|机会|风险|估值|行情|表现|值得买吗|能买吗|值得买|能买|还能涨|会涨|会跌|能不能|的话|吗|呢|吧|嘛|了|的|啊|呀)+$/

/** 真实股票名几乎不含的虚词/指代字（含任一即判非实体，防把句子片段当名字）。 */
const STOP_CHARS_RE = /[我你您他她它们这那哪吗呢吧嘛啊呀了的是和与跟对把被就都很还才刚要想问请]/

/**
 * 公司名常见后缀白名单（核心串以其结尾才视为候选；不收单字后缀，防误抽）。
 * 覆盖不到的名字宁可放弃（后端解析兜底），不放宽标准。
 */
const NAME_SUFFIX_RE =
  /(?:微电子|微电|半导体|科技|电子|电器|电气|机械|软件|网络|传媒|通信|通讯|生物|医药|药业|医疗|器械|银行|证券|保险|能源|电力|汽车|钢铁|水泥|化工|化纤|集团|控股|光电|重工|精密|智能|环保|航空|物流|食品|乳业|数码|信息|数据|时代|地产|置业|股份|实业|材料|环境|动力)$/

/**
 * 保守中文公司名启发式：剥掉首尾口水/疑问词后，核心串须为 2-6 字纯中文、
 * 不含虚词、以公司名后缀结尾、且长于后缀本身（防「股份」这类裸后缀）。
 * 通富微电/中兴通讯/歌尔股份类可命中；寒武纪/京东方类放弃（不误抽）。
 */
function extractChineseName(q: string): string | undefined {
  for (const run of q.match(HAN_RUN_RE) ?? []) {
    let prev = ''
    let core = run
    while (core !== prev) {
      prev = core
      core = core.replace(LEADING_FILLER_RE, '').replace(TRAILING_FILLER_RE, '')
    }
    if (core.length < 2 || core.length > 6) continue
    if (STOP_CHARS_RE.test(core)) continue
    const suffix = core.match(NAME_SUFFIX_RE)
    if (!suffix || core.length <= suffix[0].length) continue
    return core
  }
  return undefined
}


const PROCESS_STEPS: Record<XcIntentKind, string[]> = {
  analyze: [
    '识别标的范围与问题类型',
    '拉取行情 / 基本面 / 资金面多源数据',
    '综合研判并生成结构化结论',
    '标注引用来源 [S#]',
  ],
  compare: [
    '解析对比标的与对比维度',
    '对齐时间序列与统计口径',
    '逐维对比并给出相对强弱',
    '汇总结论与适用场景',
  ],
  explain: [
    '定位问题概念与知识边界',
    '拆解因果链与关键变量',
    '用通俗语言重构解释',
    '给出可验证的延伸阅读',
  ],
  debate: [
    '构建多空双方论点框架',
    '分别举证与交叉反驳',
    '评估论据权重与确定性',
    '给出平衡结论与风险点',
  ],
  data: [
    '定位所需财务 / 行情字段',
    '校验数据时效与口径',
    '计算关键比率与趋势',
    '输出数值化结论',
  ],
  general: [
    '解析用户意图',
    '检索相关知识与数据',
    '组织结构化回答',
  ],
}

const CHIPS: Record<XcIntentKind, string[]> = {
  analyze: ['技术面怎么看？', '现在能上车吗？', '主要风险有哪些？'],
  compare: ['哪个更值得配置？', '估值差多少？', '资金面谁更强？'],
  explain: ['用小白能懂的话讲', '有哪些数据支撑？', '和普通认知有什么不同？'],
  debate: ['看多方逻辑是什么？', '看空方逻辑是什么？', '概率更偏向哪边？'],
  data: ['近三年趋势如何？', '同业对比怎样？', '未来催化有哪些？'],
  general: ['展开说说', '举个实例', '需要注意什么？'],
}

function hasCode(q: string): boolean {
  return /\b\d{6}\b/.test(q)
}

function hasEntity(q: string): boolean {
  return ENTITY_KEYWORDS.some((k) => q.includes(k))
}

/**
 * 纯寒暄 / 纯语气词（无任何分析实义）——只有这类输入才前端追问补参。
 *
 * 诚实红线：后端 ai_answer 自带「没找到标的给诚实引导」兜底（modules/ai_engine.py:703-711），
 * 前端无权替后端拒答。中文股票名（如「通富微电」）、2-6 字实体、泛泛提问一律放行给后端，
 * 由后端解析 / 兜底；hasCode / hasEntity 只用于意图分类与主题抽取，不再作为拦截条件。
 * 宁可放行给后端兜底，不可前端误拦截真实提问。
 */
const NO_SUBSTANCE_RE =
  /^(?:你好|您好|哈喽|嗨|喂|在吗|在么|早上好|晚上好|hi|hello|hey|yo|谢谢|感谢|多谢|thanks|thx|嗯+|哦+|噢+|额+|呃+|啊+|呀+|哈+|吼+|好+|行+|ok|okay)[!！。.?,，~～\s]*$/i

function isNoSubstance(q: string): boolean {
  return q.length === 0 || NO_SUBSTANCE_RE.test(q)
}

function detectKind(q: string): XcIntentKind {
  const t = q.toLowerCase()
  if (/对比|比较|vs|孰强|哪个好|谁更强|pk|对决/.test(q) && (hasCode(q) || hasEntity(q))) {
    return 'compare'
  }
  if (/多空|看涨|看跌|看多|看空|后市|辩论|牛熊|涨跌/.test(q)) {
    return 'debate'
  }
  if (/数据|财务|业绩|营收|利润|估值|pe|pb|roe|毛利率|负债|现金流|分红/.test(t)) {
    return 'data'
  }
  if (/分析|研判|怎么样|如何看|值得|能买|机会|风险|投资|操作|持仓|止损/.test(q)) {
    return 'analyze'
  }
  if (/为什么|怎么|如何|原理|逻辑|解释|教学|什么叫|是什么|区别|入门/.test(q)) {
    return 'explain'
  }
  if (hasCode(q) || hasEntity(q)) {
    return 'analyze'
  }
  return 'general'
}

export function classifyIntent(question: string): XcIntent {
  const q = (question || '').trim()
  const kind = detectKind(q)
  // 仅对无实义输入追问；真实提问（含中文股票名）一律放行给后端兜底
  const needsParam = isNoSubstance(q)
  return {
    kind,
    label: KIND_LABELS[kind],
    // 确定性规则：命中关键词越多置信越高；general/缺参时压低置信，避免伪造确定性
    confidence: needsParam ? 0.3 : kind === 'general' ? 0.55 : 0.82,
    processSteps: PROCESS_STEPS[kind],
    suggestionChips: needsParam ? [] : CHIPS[kind],
    needsParam,
    paramPrompts: needsParam
      ? [
          '请补充你想分析的股票代码（6 位）或名称',
          '或说明想聊的市场 / 板块方向',
        ]
      : [],
  }
}
