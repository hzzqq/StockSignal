import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { NAV } from '@/nav/nav'
import { Card } from '@/shared/ui/Card'

/**
 * 新手教程（/guide）—— v1 `96_新手教程.py` 的 v2 等价页面。
 *
 * 纯 UI / 引导层，不涉及任何行情数字，也不改动业务逻辑；所有说明均对应
 * 本仓已有实现，不编造功能。上手进度真实写入浏览器 localStorage，
 * 不谎称同步到账号。v1 的教学视频与 Streamlit 原生快捷键不适用 React SPA，
 * 明确说明「未移植」，不做假入口。
 */
const STORAGE_KEY = 'ss_guide_steps'

const STEPS = [
  { id: 'decision', title: '看一遍今日决策面板', to: '/decision', desc: '先理解「数据日 → 情绪 → 建议仓位」这条主线。' },
  { id: 'diagnostics', title: '确认数据源与接口状态', to: '/diagnostics', desc: '数据源、时效与端点清单如实列出；默认不主动探网。' },
  { id: 'catalog', title: '逛一次 v1 功能全景', to: '/catalog', desc: '74 页全部可发现，三档状态如实标注「列出 ≠ 已实现」。' },
  { id: 'settings', title: '到设置里调好主题与密度', to: '/settings', desc: '偏好只保存在此浏览器；当前是真实后端还是开发模拟数据也在这里看。' },
] as const

/** 差异化主线（对应 v1 96 页 §1.5）：只链接 v2 真实存在的路由，缺等价页的一步如实说明。 */
const MAINLINE = [
  { step: '① 采情绪', name: '市场广度与温度', to: '/breadth', desc: '从涨跌家数、涨停/跌停、红盘占比等广度维度感受市场状态。' },
  { step: '② 出决策', name: '今日决策面板', to: '/decision', desc: '温度 + 方向 + 周期 + 事件因子收敛成「今日几成仓」建议（有上下界）。' },
  { step: '③ 验对错', name: '预测校准日志 / 决策回放', to: '/predictions', desc: '把落盘的预测与真实走势对照，看方向是否命中；历史决策可回放。' },
  // v2 暂无「仓位刻度校准」等价页，如实指向功能全景而不是编造一个链接。
  { step: '④ 校刻度', name: '仓位刻度校准', to: '/catalog', desc: 'v2 暂无等价页面，功能全景中如实标为「仅 v1」；样本不足时只观察、不采纳。' },
] as const

const GLOSSARY: { term: string; desc: string }[] = [
  { term: '红涨绿跌', desc: '交易屏的价格域配色：上涨红、下跌绿；报告与个股页另用绿涨红跌，两套语义不可混用。' },
  { term: '报告体配色', desc: '研报/个股页沿用文档习惯的绿涨红跌，与交易屏相反。' },
  { term: '归一化', desc: '把不同量纲的指标统一到起点=100 再叠加比较，避免数值大小掩盖形状差异。' },
  { term: '回测', desc: '用历史数据检验规则；项目如实披露方向命中率≈随机，价值在筛选漏斗与风控。' },
  { term: '情绪温度', desc: '由市场广度等维度合成的市场状态刻度，冰点与过热都是历史统计口径，不是买卖信号。' },
  { term: '连板梯队晋级率', desc: '连板高度结构的日度统计；离线数据缺真值的维度会被剔除，不编造。' },
  { term: '决策仓位', desc: '按规则对各因子打分后收敛出的建议仓位，已做上下界约束。' },
  { term: '互相关', desc: '两条序列形状的相似度；只描述协同/错位，非因果、非预测。' },
]

/** 常见误区（对应 v1 96 页 §4.5），措辞按 v2 真实现状校准。 */
const PITFALLS = [
  { title: '把回测命中率当成「策略领先」', desc: '方向命中率≈随机是项目如实披露的结论，不能包装成胜率优势；价值在于漏斗与风控。' },
  { title: '拿情绪温度当买卖信号', desc: '温度是历史统计刻度，只描述市场状态；冰点/过热的历史统计不等于次日必涨必跌。' },
  { title: '把互相关当因果或预测', desc: '领先-滞后矩阵只说明两条序列形状相似与错位，不构成因果，也不能预测方向。' },
  { title: '忽略派生维度的机械相关', desc: '红盘占比由涨跌平家数直接算出，它们之间的高相关部分是构造使然，不是独立发现。' },
  { title: '样本不足就下结论', desc: '刻度校准、矩阵计算都有样本下限；样本不足时只观察、不采纳，页面会如实列出被剔除项。' },
  { title: '混用两套涨跌配色', desc: '交易屏红涨绿跌、报告体绿涨红跌；强弱信号灯又是另一套语义，别按颜色直觉推断涨跌。' },
]

const FAQ: { q: string; a: string }[] = [
  { q: 'v2 和 v1 是什么关系？', a: 'v2 是新的 React 前端。功能全景把 v1 的 74 页全部纳入可发现入口，并如实分成「已实现 / 关联数据 / 仅 v1」三档，列出不等于已实现。' },
  { q: '为什么有些数据是空的或显示「—」？', a: '取不到就显示空或「—」，绝不补 0、绝不拿当前日期冒充数据日。缺失字段会逐项独立降级。' },
  { q: '开发模拟数据（MSW）是什么？', a: '开发态可用夹具模拟响应；设置页会显示当前模式，检测页与数据浏览器也会标注模拟结果，不代表真实后端数据。' },
  { q: '接口检测的探测结果可信吗？', a: '默认零网络、不发真实探测；点「重新探测」才会逐源检查，失败项独立降级并如实显示。需参数的端点不会被误判为故障。' },
  { q: '设置会同步到我的账号吗？', a: '不会。主题、密度与 v1 地址只写入本浏览器 localStorage，不写后端，也不谎称已同步。' },
  { q: '新手教程和 v1 完全一样吗？', a: '四步上手、模块导览、术语表、常见问题、差异化主线、常见误区都已移植；v1 的教学视频与 Streamlit 原生快捷键不适用于 React 单页应用，未移植，也不放假入口。' },
]

function readDone(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed)
      ? parsed.filter((x): x is string => typeof x === 'string')
      : []
  } catch {
    return []
  }
}

export function GuideView() {
  const [done, setDone] = useState<string[]>(readDone)
  const [faqQuery, setFaqQuery] = useState('')
  const pct = Math.round((done.length / STEPS.length) * 100)
  const faqs = FAQ.filter((f) =>
    `${f.q} ${f.a}`.toLowerCase().includes(faqQuery.trim().toLowerCase()),
  )

  function toggle(id: string) {
    const next = done.includes(id) ? done.filter((x) => x !== id) : [...done, id]
    setDone(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">新手教程</h2>
        <span className="text-label text-sf-ink-3">5 分钟上手 · 进度保存在此浏览器</span>
      </div>

      <Card title="四步上手" right={<span className="text-label text-sf-ink-3 tabular-nums">{done.length} / {STEPS.length} · {pct}%</span>}>
        <div className="flow">
          <div role="progressbar" aria-label="上手进度" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
            className="h-1.5 w-full rounded-tile bg-sf-surface-2 overflow-hidden">
            <div className="h-full bg-sf-accent" style={{ width: `${pct}%` }} />
          </div>
          {STEPS.map((s) => (
            <label key={s.id} className="flex flex-wrap items-start gap-3 py-1.5 text-body text-sf-ink-2">
              <input
                type="checkbox"
                checked={done.includes(s.id)}
                onChange={() => toggle(s.id)}
                aria-label={s.title}
                className="mt-1"
              />
              <span className="min-w-[10rem] text-sf-ink">{s.title}</span>
              <span className="flex-1 text-label text-sf-ink-3">{s.desc}</span>
              <Link to={s.to} className="text-label text-sf-accent hover:underline">前往 →</Link>
            </label>
          ))}
        </div>
      </Card>

      <Card title="差异化主线速览" right={<span className="text-label text-sf-ink-3">情绪 → 决策 → 验对错 → 校刻度</span>}>
        <div className="flow">
          <p className="m-0 text-label text-sf-ink-3">
            看盘、选股、回测是通用能力；本项目真正的差异是「把建议记下来、用真实走势打分、再反推规则」这条闭环。
          </p>
          {MAINLINE.map((m) => (
            <div key={m.step} className="flex flex-wrap items-start gap-3 py-1">
              <span className="w-20 shrink-0 text-body text-sf-ink">{m.step}</span>
              <span className="min-w-[9rem] text-body text-sf-ink-2">{m.name}</span>
              <span className="flex-1 text-label text-sf-ink-3">{m.desc}</span>
              <Link to={m.to} className="text-label text-sf-accent hover:underline">前往 →</Link>
            </div>
          ))}
        </div>
      </Card>

      <Card title="模块导览" right={<span className="text-label text-sf-ink-3">与左侧导航同源</span>}>
        <div className="flow">
          {NAV.map((g) => (
            <div key={g.group} className="flex flex-wrap items-start gap-3">
              <span className="w-24 shrink-0 text-label text-sf-ink-3">{g.group}</span>
              <div className="flex flex-1 flex-wrap gap-x-4 gap-y-1">
                {g.items.map((it) => (
                  <Link key={it.to} to={it.to} className="text-body text-sf-accent hover:underline">
                    {it.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="术语表">
        <div className="overflow-x-auto">
          <table className="cat-table w-full text-body border-collapse">
            <caption className="sr-only">常用术语说明</caption>
            <thead>
              <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                <th scope="col" className="text-left py-1.5 pr-3 font-normal">术语</th>
                <th scope="col" className="text-left py-1.5 font-normal">说明</th>
              </tr>
            </thead>
            <tbody className="text-sf-ink-2">
              {GLOSSARY.map((g) => (
                <tr key={g.term} className="border-b border-sf-line last:border-0">
                  <td className="py-1.5 pr-3 text-sf-ink whitespace-nowrap">{g.term}</td>
                  <td className="py-1.5">{g.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="常见误区" right={<span className="text-label text-sf-ink-3">共 {PITFALLS.length} 条</span>}>
        <ul className="m-0 list-none p-0 flow">
          {PITFALLS.map((p) => (
            <li key={p.title} className="border-b border-sf-line last:border-0 py-1.5">
              <div className="text-body text-sf-ink">⚠️ {p.title}</div>
              <div className="text-label text-sf-ink-3">{p.desc}</div>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="常见问题" right={<span className="text-label text-sf-ink-3">共 {faqs.length} 条</span>}>
        <div className="flow">
          <input
            type="search"
            aria-label="搜索常见问题"
            value={faqQuery}
            onChange={(e) => setFaqQuery(e.target.value)}
            placeholder="输入关键词筛选"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
          />
          {faqs.length === 0 ? (
            <p role="status" className="text-body text-sf-ink-3">没有匹配的问题，请换个关键词。</p>
          ) : (
            faqs.map((f) => (
              <details key={f.q} className="border-b border-sf-line last:border-0 py-2">
                <summary className="text-body text-sf-ink cursor-pointer">{f.q}</summary>
                <p className="text-label text-sf-ink-2 mt-2">{f.a}</p>
              </details>
            ))
          )}
        </div>
      </Card>

      <p className="text-label text-sf-ink-3">
        与 v1 的差异：教学视频与 Streamlit 原生快捷键说明未移植（React 单页应用不适用），不做假入口；
        上手进度只写此浏览器的 localStorage，不跨设备、不写账号。
      </p>
    </div>
  )
}
