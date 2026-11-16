import { HttpResponse } from 'msw'

/**
 * 写端点 MSW 演示态统一信封（严格对齐 backend/utils/response.py::_ok_payload）。
 * 与 handlers.ts 里的局部 ok/badRequest 同形状；独立成文件是为了让各 feature 的
 * 写端点 handler 可以分文件注册，而不必都挤进 handlers.ts 造成合并冲突。
 *
 * ⚠️ code 是字符串业务码（真后端默认 "ok"），不是数字 0。
 */
export function writeOk(data: unknown, message = 'ok') {
  return HttpResponse.json({ status: 'ok', code: 'ok', message, data })
}

/**
 * 参数校验失败：HTTP **422**（不是 400）。
 *
 * 2026-11-16 真实 Flask test_client 实证（E:/tmp/ss_parity_api_probe.log）：
 * backend/utils/errors.py::ValidationError 统一映射 422，实测
 * POST /api/watchlist {}、/api/price-alerts 缺 target_price、
 * /api/forum/posts 空标题、/api/auth/avatar 非 data URL 全部 422 +
 * code='validation_error'。旧写 400 会让 MSW 演示态与真后端契约漂移。
 */
export function writeBadRequest(message: string) {
  return HttpResponse.json(
    { status: 'error', code: 'validation_error', message, data: null },
    { status: 422 },
  )
}

/** 越权（如非管理员触发市场告警扫描）：HTTP 403 + code='forbidden'。 */
export function writeForbidden(message = '无权限访问') {
  return HttpResponse.json(
    { status: 'error', code: 'forbidden', message, data: null },
    { status: 403 },
  )
}

export function writeNotFound(label: string) {
  return HttpResponse.json(
    { status: 'error', code: 'not_found', message: `资源不存在：${label}`, data: null },
    { status: 404 },
  )
}

/** 演示态固定时间戳：不使用机器当前时间冒充数据日（honest-data 守卫）。 */
export const MOCK_WRITE_TS = '2026-01-01T08:00:00Z'
