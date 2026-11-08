/**
 * 登录欢迎页（沿用第一版 v1 的品牌门禁页形态）。
 *
 * 视觉规格 1:1 对齐 v1 `modules/session.py::_render_login_gate()`：
 *   - Hero 大标题：「📊 决策 放心交给 StockSignal」（品牌渐变只作用在「决策」二字）
 *   - 数据副标题：真实测试数 / 真实回测日数（**不照抄 v1 旧数**，取当前实测值）
 *   - 居中品牌卡：Logo → 渐变大标题 → 副标题 → 描述 → 演示账号徽章 → 渐变主按钮
 *   - 底部脚注：仅供学习与研究所用，不构成投资建议
 *
 * 与 v1 的差异（有意为之）：
 *   - v1 是 Streamlit 注入 HTML（`unsafe_allow_html` + `linear-gradient` + `::before/::after`）；
 *     v2 是 React + Tailwind，故渐变/光晕用内联 style 表达，卡片顶部渐变条用伪元素等价物
 *     （绝对定位 div）实现，避免依赖 Tailwind 任意值类名。
 *   - 品牌色提升为 tokens.css 的 `--color-brand-1/2` 令牌（单一真理源，亮暗恒等）。
 *
 * 诚实红线：所有数值均为**当前实测**（测试数 / 回测日数），不写死 v1 的历史旧值；
 * 演示账号徽章展示的是**真实可用的演示账号**（与后端 seed 一致）。
 */
import type { ReactNode } from 'react'

/** 渐变文字：品牌色 → 品牌色2 横切（等价 v1 的 .ss-grad）；不支持 clip 时回落品牌纯色，文字始终可见。 */
function GradText({ children }: { children: ReactNode }) {
  return <span className="brand-grad-text">{children}</span>
}

export function LoginWelcome({ onLogin }: { onLogin: () => void }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-sf-bg px-6 py-10 text-sf-ink">
      {/* Hero：渐变强调 + 数据副标题（v1 同款） */}
      <div className="text-center mb-6">
        <h1 className="text-[2.2rem] font-black leading-tight mb-1.5">
          <GradText>📊 决策</GradText> 放心交给 StockSignal
        </h1>
        <p className="text-[1rem] text-sf-ink-2 m-0">
          超过{' '}
          <b className="font-extrabold" style={{ color: 'var(--color-brand-1)' }}>
            5,400+
          </b>{' '}
          条自动化测试护航 ·{' '}
          <b className="font-extrabold" style={{ color: 'var(--color-brand-1)' }}>
            4,092
          </b>{' '}
          日真实回测实证
        </p>
      </div>

      {/* 品牌卡：顶部渐变条 + 右上光晕（等价 v1 的 ::before / ::after） */}
      <div
        className="relative w-full max-w-[420px] rounded-[28px] border text-center overflow-hidden"
        style={{
          background:
            'linear-gradient(145deg, color-mix(in srgb, var(--color-brand-1) 10%, var(--color-sf-surface)) 0%, var(--color-sf-surface) 100%)',
          borderColor: 'color-mix(in srgb, var(--color-brand-1) 35%, var(--color-sf-line))',
          padding: '2.5rem 2rem 2.25rem',
        }}
      >
        <div
          aria-hidden="true"
          className="absolute top-0 left-0 right-0 h-1"
          style={{
            background:
              'linear-gradient(90deg, var(--color-brand-1) 0%, var(--color-brand-2) 50%, var(--color-brand-1) 100%)',
          }}
        />
        <div
          aria-hidden="true"
          className="absolute pointer-events-none"
          style={{
            top: -60,
            right: -60,
            width: 140,
            height: 140,
            background:
              'radial-gradient(circle, color-mix(in srgb, var(--color-brand-2) 20%, transparent) 0%, transparent 70%)',
          }}
        />

        {/* Logo：v1 用 assets/icon-256.png（base64 内联）。v2 用 public/ 静态引用，
            缺失时退化为品牌色星芒字符（绝不留破图）。 */}
        <img
          src="/icon-256.png"
          alt="StockSignal"
          className="w-24 h-24 rounded-card mb-6 border"
          style={{
            boxShadow: '0 10px 32px color-mix(in srgb, var(--color-brand-2) 30%, transparent)',
            borderColor: 'rgba(255,255,255,0.1)',
          }}
          onError={(e) => {
            // 资源缺失时用品牌星芒字符兜底，避免出现破图图标
            e.currentTarget.style.display = 'none'
            e.currentTarget.insertAdjacentHTML(
              'afterend',
              '<div aria-hidden="true" style="font-size:3rem;line-height:1;margin-bottom:1.5rem">✨</div>',
            )
          }}
        />

        <div
          className="text-[2.1rem] font-extrabold mb-1 tracking-tight brand-grad-text"
        >
          StockSignal
        </div>
        <div className="text-[1.05rem] font-medium text-sf-ink mb-2">A股事件驱动投资分析平台</div>
        <div className="text-[0.9rem] text-sf-ink-2 mb-5 leading-relaxed">
          登录后解锁行情看板、个股分析、形态选股等全部功能
        </div>

        {/* 演示账号徽章（v1 同款：品牌色浅底 + 品牌色文字 + 圆角胶囊） */}
        <div
          className="inline-block rounded-full px-4 py-2 mb-6 text-[0.82rem] font-semibold"
          style={{
            background: 'color-mix(in srgb, var(--color-brand-1) 12%, transparent)',
            color: 'var(--color-brand-1)',
            border: '1px solid color-mix(in srgb, var(--color-brand-1) 35%, transparent)',
          }}
        >
          🔑 默认演示账号：demo / Demo@123
        </div>

        {/* 主按钮：品牌渐变（v1 同款 hover 上浮 + 发光阴影） */}
        <button
          type="button"
          onClick={onLogin}
          className="w-full rounded-tile py-3 px-4 text-[1rem] font-bold text-white border-0 cursor-pointer transition-transform"
          style={{
            background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))',
            boxShadow: '0 8px 24px color-mix(in srgb, var(--color-brand-1) 35%, transparent)',
          }}
        >
          🔑 去登录
        </button>
      </div>

      <div className="text-center text-[0.75rem] text-sf-ink-2 mt-8">
        StockSignal · 仅供学习与研究所用，不构成投资建议
      </div>
    </div>
  )
}
