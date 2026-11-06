import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

/** 启动浏览器端 MSW（开发模式演示数据）。 */
export async function startMockWorker() {
  const worker = setupWorker(...handlers)
  await worker.start({ onUnhandledRequest: 'bypass' })
}
