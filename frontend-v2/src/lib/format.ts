/** 数值格式化：null/undefined → 占位符「—」；整数原样、浮点保留两位。禁止补零造假。 */
export function fmtNum(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
  return String(v)
}
