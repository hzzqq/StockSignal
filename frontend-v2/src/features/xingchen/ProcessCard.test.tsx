import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProcessCard } from './ProcessCard'

describe('ProcessCard（问题分析卡）', () => {
  const steps = ['识别标的', '拉取数据', '生成结论']

  it('默认折叠：步骤不渲染', () => {
    render(<ProcessCard steps={steps} />)
    expect(screen.queryByText('识别标的')).toBeNull()
  })

  it('点击展开后渲染步骤', () => {
    render(<ProcessCard steps={steps} />)
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByText('识别标的')).toBeTruthy()
    expect(screen.getByText('生成结论')).toBeTruthy()
  })

  it('defaultOpen 时直接展开', () => {
    render(<ProcessCard steps={steps} defaultOpen />)
    expect(screen.getByText('拉取数据')).toBeTruthy()
  })
})
