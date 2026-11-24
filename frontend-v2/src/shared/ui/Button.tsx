import type { ButtonHTMLAttributes, ReactNode } from 'react'

/**
 * 精致层次档 · 通用按钮。
 * 只用语义令牌：品牌渐变 / 实色表面 / 状态色；绝不借 A 股涨跌色做装饰。
 * 焦点环沿用全局 :focus-visible（tokens.css），此处补一层 ring 强化可读性。
 */
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
}

const cx = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ')

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary:
    'border border-transparent bg-gradient-to-r from-brand-1 to-brand-2 text-white hover:brightness-110',
  secondary:
    'border border-sf-line bg-sf-surface-2 text-sf-ink hover:bg-sf-surface',
  ghost:
    'border border-transparent bg-transparent text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink',
  danger:
    'border border-transparent bg-sf-danger-soft text-sf-danger hover:brightness-110',
}

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-label',
  md: 'h-9 px-3.5 text-body',
}

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  type,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type ?? 'button'}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-tile font-medium transition-[background-color,border-color,box-shadow,color,filter] hover:shadow-e2 focus-visible:ring-2 focus-visible:ring-sf-accent disabled:pointer-events-none disabled:opacity-50',
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      )}
    >
      {children}
    </button>
  )
}
