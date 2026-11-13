/**
 * 模型徽标 · 诚实态：后端未配置 LLM 时显「规则引擎模式」，不伪装具体模型。
 * 跟随 data-theme（仅用语义令牌，两主题恒等）。
 */
export function ModelBadge({ model }: { model?: string }) {
  const configured = !!model && model.trim().length > 0
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-tile border border-sf-line bg-sf-surface-2 px-2.5 py-1 text-label text-sf-ink-3"
      title={configured ? `当前模型：${model}` : '后端未配置 LLM，走规则引擎'}
    >
      <span aria-hidden="true">🤖</span>
      {configured ? model : '规则引擎模式'}
    </span>
  )
}
