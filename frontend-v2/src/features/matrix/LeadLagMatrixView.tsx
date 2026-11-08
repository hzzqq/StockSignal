import { useMemo } from 'react'
import { useBreadthHistory } from '@/lib/queries'
import {
  buildMatrix, signedLag, DERIVED_NOTICE, DIMENSIONS, EXCLUDED_DIMENSIONS,
  MIN_SAMPLES, MIN_PAIR_SAMPLES, MAX_LAG,
} from '@/lib/leadLag'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'

/**
 * 维度领先-滞后矩阵（/matrix）—— v1 `66_维度领先滞后矩阵.py` 的 v2 等价页面。
 *
 * 数据来自真实只读端点 /api/v2/read/breadth-history（shepherd_history 逐日广度）。
 * 诚实红线：
 *  - 与 v1 一样输出**有序对**结果，带符号 lag 表示同向/反向领先；
 *  - 互相关仅描述协同/错位，**非因果、非预测**；
 *  - 红盘占比由涨跌平家数派生，机械相关必须显式告知；
 *  - 连板梯队类维度离线缺真值已剔除；样本不足的维度/维度对如实列出；
 *  - 取不到数据就显示空态，不补 0、不编造相关系数。
 */
export function LeadLagMatrixView() {
  const history = useBreadthHistory()
  const matrix = useMemo(() => buildMatrix(history.data ?? []), [history.data])
  const enough = matrix.rows.length > 0

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">维度领先滞后矩阵</h2>
        <span className="text-label text-sf-ink-3">
          真实广度日序列 · 错位窗口 0–{MAX_LAG} 个交易日
        </span>
      </div>

      <Card title="统计口径与数据边界">
        <div className="flow text-body text-sf-ink-2">
          <p className="m-0">
            每条结果是一个<strong className="text-sf-ink">有序对</strong>：lag=k 表示「前者取 t 日、后者取 t+k 日」，
            即前者领先 k 个交易日；取 |corr| 最大的错位。表中 lag 带符号：
            正相关记 +k（同向领先），负相关记 −k（反向领先），与 v1 矩阵单元格口径一致。
            <strong className="text-sf-ink">互相关只描述协同/错位，非因果、非预测</strong>。
          </p>
          <p className="m-0">
            参与计算的离线可靠维度：{DIMENSIONS.map((d) => d.label).join(' / ')}。
            每维度至少需要 {MIN_SAMPLES} 个有效交易日，每个 lag 至少需要 {MIN_PAIR_SAMPLES} 个成对样本；
            皮尔逊相关本身即 z-score 归一后的协方差，与 v1 的显式 z-score 数学等价。
          </p>
          <p className="m-0 text-sf-warn">⚠️ {DERIVED_NOTICE}</p>
          <p className="m-0 text-label text-sf-ink-3">
            已剔除（离线缺真值，不编造）：{EXCLUDED_DIMENSIONS.map((d) => d.label).join(' / ')}。
          </p>
          <p className="m-0 text-label text-sf-ink-3">
            与 v1 的差异：v1 用「非空率 ≥20% + 每 lag ≥3 样本」闸门并输出热力图；
            v2 采用更严格的 ≥{MIN_SAMPLES} / ≥{MIN_PAIR_SAMPLES} 样本下限并输出有序对明细表，
            样本不足者一律列出，不静默消失。
          </p>
          {matrix.firstDate ? (
            <p className="m-0 text-label text-sf-ink-3">
              样本区间 {matrix.firstDate} – {matrix.lastDate} · 共 {matrix.totalDays} 个交易日 ·
              至少含一个有效维度的 {matrix.usableDays} 日
            </p>
          ) : null}
          {matrix.excluded.length > 0 ? (
            <p className="m-0 text-label text-sf-warn">
              未参与计算的可靠维度：
              {matrix.excluded.map((d) => `${d.label}（${d.reason}）`).join('、')}
            </p>
          ) : null}
          {matrix.skippedPairs.length > 0 ? (
            <p className="m-0 text-label text-sf-warn">
              样本不足而未产出结果的维度对（{matrix.skippedPairs.length} 对）：
              {matrix.skippedPairs.slice(0, 6).map((p) => `${p.xLabel}→${p.yLabel}`).join('、')}
              {matrix.skippedPairs.length > 6 ? ' 等' : ''}；原因：{matrix.skippedPairs[0].reason}。
            </p>
          ) : null}
        </div>
      </Card>

      <QueryState
        isLoading={history.isLoading}
        isError={history.isError}
        error={history.error}
        isEmpty={!history.isLoading && !history.isError && !enough}
        emptyLabel="有效样本不足，未计算矩阵"
        emptyHint={`每个维度至少需要 ${MIN_SAMPLES} 个有效交易日、每个 lag 至少需要 ${MIN_PAIR_SAMPLES} 个成对样本；取不到真实广度日序列时如实留空，不编造相关系数。`}
      >
        <Card title="两两维度最优领先-滞后（有序对）" right={<span className="text-label text-sf-ink-3">共 {matrix.rows.length} 组</span>}>
          <div className="overflow-x-auto">
            <table className="cat-table w-full text-body border-collapse">
              <caption className="sr-only">广度维度有序对互相关的最优错位</caption>
              <thead>
                <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                  <th scope="col" className="text-left py-1.5 pr-3 font-normal">维度（前者 → 后者）</th>
                  <th scope="col" className="text-left py-1.5 pr-3 font-normal">带符号 lag</th>
                  <th scope="col" className="text-left py-1.5 pr-3 font-normal">相关系数</th>
                  <th scope="col" className="text-left py-1.5 pr-3 font-normal">成对样本</th>
                  <th scope="col" className="text-left py-1.5 font-normal">解读</th>
                </tr>
              </thead>
              <tbody className="text-sf-ink-2">
                {matrix.rows.map((r) => (
                  <tr key={`${r.x}-${r.y}`} className="border-b border-sf-line last:border-0">
                    <td className="py-1.5 pr-3">{r.xLabel} → {r.yLabel}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{signedLag(r) > 0 ? `+${signedLag(r)}` : signedLag(r)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{r.corr.toFixed(3)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{r.samples}</td>
                    <td className="py-1.5">
                      {r.lag === 0
                        ? '同步变动'
                        : `${r.xLabel} 领先 ${r.yLabel} ${r.lag} 个交易日（${r.corr >= 0 ? '同向' : '反向'}）`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-label text-sf-ink-3 mt-3">
            相关系数绝对值大只说明两条序列形状相似，不代表能预测次日涨跌；
            派生维度之间的高相关还可能是机械相关（见上方警示）。
          </p>
        </Card>
      </QueryState>
    </div>
  )
}
