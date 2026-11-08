import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// 每个用例后卸载 React 树，避免跨用例 DOM 残留。
afterEach(() => {
  cleanup()
})
