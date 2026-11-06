import { describe, it, expect } from 'vitest'
import { handlers } from '@/mocks/handlers'

describe('msw handlers', () => {
  it('导出为数组且非空', () => {
    expect(Array.isArray(handlers)).toBe(true)
    expect(handlers.length).toBeGreaterThan(0)
  })
})
