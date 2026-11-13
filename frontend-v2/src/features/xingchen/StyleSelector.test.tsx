import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StyleSelector } from './StyleSelector'

describe('StyleSelector', () => {
  it('默认选中 quick', () => {
    render(<StyleSelector value="quick" onChange={() => {}} />)
    expect(screen.getByText('快速问答').closest('button')?.getAttribute('aria-checked')).toBe('true')
  })

  it('点击辩论 → onChange(debate)', () => {
    const onChange = vi.fn()
    render(<StyleSelector value="quick" onChange={onChange} />)
    fireEvent.click(screen.getByText('多空辩论'))
    expect(onChange).toHaveBeenCalledWith('debate')
  })
})
