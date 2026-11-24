import { useId } from 'react'
import type {
  InputHTMLAttributes,
  TextareaHTMLAttributes,
  SelectHTMLAttributes,
  ReactNode,
} from 'react'

/**
 * 精致层次档 · 统一表单控件：Input / Textarea / Select。
 * 三者均受控（value / onChange 透传），组件内部不藏状态。
 * className 作用于外层 wrapper，便于页面统一宽度；控件本体样式由令牌锁定。
 */
interface FieldCommonProps {
  label?: string
  error?: string
  hint?: string
  className?: string
}

export interface InputFieldProps
  extends InputHTMLAttributes<HTMLInputElement>, FieldCommonProps {}
export interface TextareaFieldProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement>, FieldCommonProps {}
export interface SelectFieldProps
  extends SelectHTMLAttributes<HTMLSelectElement>, FieldCommonProps {
  children?: ReactNode
}

const cx = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ')

const BASE =
  'w-full rounded-tile border bg-sf-bg px-3 py-2 text-body text-sf-ink placeholder:text-sf-ink-3 hover:shadow-e1 focus:outline-none focus:ring-2 focus:ring-sf-accent transition-[border-color,box-shadow]'

function useFieldA11y(idProp: string | undefined, hasError: boolean, hasHint: boolean) {
  const autoId = useId()
  const id = idProp ?? autoId
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = hasError ? errorId : hasHint ? hintId : undefined
  return { id, hintId, errorId, describedBy }
}

function FieldFrame({
  id,
  label,
  error,
  hint,
  hintId,
  errorId,
  className,
  children,
}: {
  id: string
  label?: string
  error?: string
  hint?: string
  hintId: string
  errorId: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cx('w-full', className)}>
      {label && (
        <label htmlFor={id} className="mb-1 block text-label text-sf-ink-2">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p id={errorId} role="alert" className="mt-1 text-label text-sf-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="mt-1 text-label text-sf-ink-3">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

const controlClass = (error?: string) =>
  error
    ? 'border-sf-danger focus:border-sf-danger'
    : 'border-sf-line focus:border-sf-accent'

export function Input({
  label,
  error,
  hint,
  className,
  id,
  ...rest
}: InputFieldProps) {
  const a = useFieldA11y(id, Boolean(error), Boolean(hint))
  return (
    <FieldFrame
      id={a.id}
      label={label}
      error={error}
      hint={hint}
      hintId={a.hintId}
      errorId={a.errorId}
      className={className}
    >
      <input
        {...rest}
        id={a.id}
        aria-invalid={error ? true : undefined}
        aria-describedby={a.describedBy}
        className={cx(BASE, controlClass(error))}
      />
    </FieldFrame>
  )
}

export function Textarea({
  label,
  error,
  hint,
  className,
  id,
  ...rest
}: TextareaFieldProps) {
  const a = useFieldA11y(id, Boolean(error), Boolean(hint))
  return (
    <FieldFrame
      id={a.id}
      label={label}
      error={error}
      hint={hint}
      hintId={a.hintId}
      errorId={a.errorId}
      className={className}
    >
      <textarea
        {...rest}
        id={a.id}
        aria-invalid={error ? true : undefined}
        aria-describedby={a.describedBy}
        className={cx(BASE, 'resize-y min-h-[120px]', controlClass(error))}
      />
    </FieldFrame>
  )
}

export function Select({
  label,
  error,
  hint,
  className,
  id,
  children,
  ...rest
}: SelectFieldProps) {
  const a = useFieldA11y(id, Boolean(error), Boolean(hint))
  return (
    <FieldFrame
      id={a.id}
      label={label}
      error={error}
      hint={hint}
      hintId={a.hintId}
      errorId={a.errorId}
      className={className}
    >
      <div className="relative">
        <select
          {...rest}
          id={a.id}
          aria-invalid={error ? true : undefined}
          aria-describedby={a.describedBy}
          className={cx(BASE, 'appearance-none pr-9', controlClass(error))}
        >
          {children}
        </select>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          fill="none"
          className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-sf-ink-3"
        >
          <path
            d="m5 7.5 5 5 5-5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </FieldFrame>
  )
}
