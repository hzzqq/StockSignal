/**
 * v1 首页 Hero 移植（app.py::_render_project_intro）。
 *
 * 1:1 保留 v1 的叙事结构：眉标 → 痛点大标题 → 副标题 → 01/02/03 编号卡
 * → 金句行 → 分隔线 → 三色能力卡。差异只在实现层：v1 用 Streamlit
 * unsafe_allow_html 注入 <style>，v2 用 React + 设计令牌（亮暗主题恒等）。
 *
 * 诚实口径：文案与 v1 完全一致（不含任何动态数字），因此不存在「照抄旧数」
 * 的问题；三枚点缀色沿用 v1 固定值，属能力标签语义，不误用 A 股涨跌色。
 */

const BRAND = 'var(--color-brand-1)'

const PAINS = [
  {
    num: '01',
    icon: '❓',
    title: '当初为什么买？',
    desc: '三个月前看好的逻辑，是基本面、技术形态，还是一时冲动？现在你还说得清吗？',
  },
  {
    num: '02',
    icon: '🎲',
    title: '赚了，是判断对还是运气？',
    desc: '赚到的钱，究竟是判断准，还是恰好赶上普涨？分不清，就无法复制。',
  },
  {
    num: '03',
    icon: '🔍',
    title: '亏了，错在哪一步？',
    desc: '前提失效？推导偏差？还是被噪音带偏？说不出来，下次还会再踩。',
  },
] as const

const CAPS = [
  {
    color: '#d29922',
    icon: '🌡️',
    title: '情绪温度计',
    tag: '每日盘后',
    desc: '牧羊人 17 项市场指标 → 情绪周期定位 + 次日方向与建议仓位，透明推导可解释。',
  },
  {
    color: '#14b8a6',
    icon: '📰',
    title: '事件驱动信号',
    tag: '三源聚合',
    desc: '产业事件 / 价格信号 / 宏观数据三类催化，自动追踪评分，快速识别行情主线。',
  },
  {
    color: '#8b5cf6',
    icon: '🧪',
    title: '决策闭环回测',
    tag: '历史验证',
    desc: '决策建议逐日归档，与次日真实走势对照回填，命中率与偏差全部如实呈现。',
  },
] as const

function brandMix(pct: number, target = BRAND): string {
  return `color-mix(in srgb, ${target} ${pct}%, transparent)`
}

export function ProjectIntro() {
  return (
    <section
      aria-labelledby="project-intro-title"
      className="intro-root mx-auto w-full max-w-[1080px] flow"
    >
      <div className="text-center">
        <span
          className="inline-block rounded-full px-4 py-1.5 text-label font-bold tracking-wide"
          style={{ color: BRAND, background: brandMix(12), border: `1px solid ${brandMix(32)}` }}
        >
          ✨ A股事件驱动 · 决策闭环
        </span>
      </div>

      <h1
        id="project-intro-title"
        className="mx-auto max-w-[880px] text-center font-extrabold text-sf-ink"
        style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.1rem)', lineHeight: 1.32, margin: '.1rem auto .7rem' }}
      >
        看了一堆分析，最后还是<span style={{ color: BRAND }}>凭感觉</span>下单
      </h1>
      <p className="mx-auto max-w-[640px] text-center text-body text-sf-ink-2" style={{ lineHeight: 1.75, margin: '0 auto 1.6rem' }}>
        赚了说不清为什么，亏了重复踩同一个坑 —— 几年下来，投资经验始终没真正积累。
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4" style={{ marginBottom: '1.4rem' }}>
        {PAINS.map((p) => (
          <div
            key={p.num}
            className="intro-pain relative rounded-card border border-sf-line bg-sf-surface transition-transform"
          >
            <span
              className="absolute font-extrabold"
              style={{ top: '.8rem', right: '1.1rem', fontSize: '1.5rem', color: brandMix(38) }}
              aria-hidden="true"
            >
              {p.num}
            </span>
            <span
              className="inline-flex items-center justify-center rounded-tile"
              style={{ width: 40, height: 40, fontSize: '1.2rem', background: brandMix(12) }}
              aria-hidden="true"
            >
              {p.icon}
            </span>
            <b className="block text-body text-sf-ink" style={{ margin: '.7rem 0 .35rem', fontSize: '1.02rem' }}>
              {p.title}
            </b>
            <small className="block text-label text-sf-ink-2" style={{ lineHeight: 1.6 }}>
              {p.desc}
            </small>
          </div>
        ))}
      </div>

      <p className="mx-auto max-w-[840px] text-center text-body text-sf-ink" style={{ lineHeight: 1.85, margin: '0 auto 1.6rem' }}>
        ✨ 问题不在信息不够，而在你的
        <span style={{ color: BRAND, fontWeight: 700 }}>判断从没被记录、验证</span>过。
        StockSignal 把<b>情绪 → 事件 → 仓位 → 复盘</b>每一步都记录下来，用回测验证，让经验真正复利。
      </p>

      <div
        aria-hidden="true"
        className="mx-auto max-w-[720px]"
        style={{ height: 1, background: 'linear-gradient(90deg, transparent, var(--color-sf-line), transparent)', margin: '1.6rem auto' }}
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {CAPS.map((c) => (
          <div
            key={c.title}
            className="rounded-card border p-4"
            style={{
              background: `color-mix(in srgb, ${c.color} 7%, var(--color-sf-surface))`,
              borderColor: `color-mix(in srgb, ${c.color} 30%, var(--color-sf-line))`,
            }}
          >
            <span className="text-title" aria-hidden="true">{c.icon}</span>
            <b className="block text-body text-sf-ink" style={{ margin: '.45rem 0 .3rem' }}>
              {c.title}
              <span
                className="ml-2 inline-block rounded-full px-2 py-0.5 align-middle font-bold"
                style={{ fontSize: '.7rem', color: c.color, background: `color-mix(in srgb, ${c.color} 12%, transparent)` }}
              >
                {c.tag}
              </span>
            </b>
            <small className="block text-label text-sf-ink-2" style={{ lineHeight: 1.6 }}>
              {c.desc}
            </small>
          </div>
        ))}
      </div>
    </section>
  )
}
