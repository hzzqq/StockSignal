/**
 * 模型徽标 · 诚实态：前端不探测后端模型配置，未显式选择模型时不声称具体模型或运行模式。
 * 仅当用户确实选过模型才显示该名字（且标明最终以服务端为准）；否则显示中性文案。
 * 跟随 data-theme（仅用语义令牌，两主题恒等）。
 */
export function ModelBadge({ model }: { model?: string }) {
  const selected = !!model && model.trim().length > 0
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-tile border border-sf-line bg-sf-surface-2 px-2.5 py-1 text-label text-sf-ink-3"
      title={
        selected
          ? `用户选择模型：${model}（最终以服务端配置为准）`
          : '前端不探测模型配置：实际由后端决定使用 LLM 或规则引擎兜底'
      }
    >
      <span aria-hidden="true">🤖</span>
      {selected ? model : '模型：跟随后端配置'}
    </span>
  )
}
