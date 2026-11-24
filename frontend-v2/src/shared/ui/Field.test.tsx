import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Input, Textarea, Select } from './Field'

describe('Field · Input / Textarea / Select 统一控件', () => {
  it('label 通过 htmlFor / id 正确关联，受控值直接渲染', () => {
    render(<Input label="股票代码" value="600519" readOnly />)
    const input = screen.getByLabelText('股票代码') as HTMLInputElement
    expect(input.value).toBe('600519')
    expect(input.id).toBeTruthy()
    expect(input.className).toContain('rounded-tile')
    expect(screen.getByText('股票代码').tagName).toBe('LABEL')
  })

  it('error：aria-invalid + aria-describedby 指向错误文案', () => {
    render(<Input label="数量" error="数量必填" value="" readOnly />)
    const input = screen.getByLabelText('数量')
    const err = screen.getByText('数量必填')
    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(input.getAttribute('aria-describedby')).toBe(err.id)
    expect(err.className).toContain('text-sf-danger')
    expect(err.getAttribute('role')).toBe('alert')
  })

  it('hint：无 error 时 aria-describedby 指向提示文案', () => {
    render(<Input label="备注" hint="仅支持数字" value="" readOnly />)
    const input = screen.getByLabelText('备注')
    const hint = screen.getByText('仅支持数字')
    expect(input.getAttribute('aria-invalid')).toBeNull()
    expect(input.getAttribute('aria-describedby')).toBe(hint.id)
    expect(hint.className).toContain('text-sf-ink-3')
  })

  it('Select 隐藏浏览器默认箭头并使用自定义 SVG 箭头', () => {
    const { container } = render(
      <Select label="周期" value="d" onChange={() => {}}>
        <option value="d">日线</option>
        <option value="w">周线</option>
      </Select>,
    )
    const select = screen.getByLabelText('周期')
    expect(select.className).toContain('appearance-none')
    expect(container.querySelector('svg[aria-hidden="true"]')).toBeTruthy()
    expect((select as HTMLSelectElement).value).toBe('d')
  })

  it('Textarea 受控值渲染且默认 resize-y / min-h-[120px]', () => {
    render(
      <Textarea label="说明" value="持仓说明" onChange={() => {}} />,
    )
    const ta = screen.getByLabelText('说明') as HTMLTextAreaElement
    expect(ta.value).toBe('持仓说明')
    expect(ta.className).toContain('resize-y')
    expect(ta.className).toContain('min-h-[120px]')
  })

  it('className 合并到 wrapper，焦点/悬停令牌在位', () => {
    const { container } = render(
      <Input label="名称" className="max-w-xs" value="x" readOnly />,
    )
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper.className).toContain('max-w-xs')
    const input = screen.getByLabelText('名称')
    expect(input.className).toContain('bg-sf-bg')
    expect(input.className).toContain('hover:shadow-e1')
    expect(input.className).toContain('focus:border-sf-accent')
  })
})
