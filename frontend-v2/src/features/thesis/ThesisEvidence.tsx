import type { ThesisEvidence, ThesisFinding } from '@/api/schemas/read'
import { useThesisEvidence } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { SectionTitle } from '@/shared/ui/EmphasisText'
import { fmtNum } from '@/lib/format'

/**
 * 毕设证据页（/thesis）—— v1 冻结不迁，本页是毕设内容在 v2 的唯一出口。
 *
 * 四块内容（数据逻辑层全部复用 modules/experiment_improvements.py，本页只展示）：
 *  ① 三算法对照实验证据（KNOWN_FINDINGS）：#1 modest / #2、#3 负向，原样透出；
 *  ② 决策闭环评估锚 49.1%（1722/3507）+ 第6章 41 快照评估（37.5%=9/24）；
 *  ③ SHAP 加性归因（基准 + Σ调节 = 最终仓位）；
 *  ④ 组合级非对称发现（防守 +9.5pp / 进攻 -8pp，闭环是风险缩放器）。
 *
 * 诚实红线（不可回退）：
 *  - 负向 verdict 如实标 negative，绝不包装成突破；缺失数值 fmtNum → '—' 不补 0；
 *  - 所有内容是**对照实验证据而非生产信号**，不进 derive_position 生产链
 *    （test_decision_model_adj 守卫锁死 #2/#3 不得施加）；
 *  - 不用涨跌色渲染算法 verdict（那是价格域语义），用中性色 + 文字标签。
 */
export function ThesisEvidenceView() {
  const q = useThesisEvidence()
  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <SectionTitle as="h2">毕设证据</SectionTitle>
        <span className="text-label text-sf-ink-3">
          三算法对照 · 决策闭环评估 · 可解释归因（实验证据，非生产信号）
        </span>
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!q.data}
        emptyLabel="毕设证据不可用"
        emptyHint="证据数据未加载，未做任何填充"
        onRetry={() => q.refetch()}
        retrying={q.isRefetching}
      >
        {q.data ? <EvidenceBody data={q.data} /> : null}
      </QueryState>
    </div>
  )
}

function EvidenceBody({ data }: { data: ThesisEvidence }) {
  const findings = data.findings
  const ch6 = data.ch6
  const shap = data.shap_attribution
  const anchor = findings.decision_closure_anchor
  const findingRows = findings.findings ?? {}
  const allFindings = Object.values(findingRows)

  return (
    <div className="flow">
      <Card title="口径声明">
        <p className="whitespace-pre-wrap text-body text-sf-ink-2">{data.note}</p>
        {findings.core_innovation_cn && (
          <p className="mt-2 text-label text-sf-ink-3">{findings.core_innovation_cn}</p>
        )}
        {findings.honest_redline && (
          <p className="mt-2 text-label text-sf-ink-3">诚实红线：{findings.honest_redline}</p>
        )}
        {findings.available === false && (
          <p className="mt-2 text-body text-sf-ink-2">实验证据加载失败：{fmtNum(findings.reason)}</p>
        )}
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="方向命中锚" value={fmtNum(anchor?.accuracy == null ? null : `${(anchor.accuracy * 100).toFixed(1)}%`)}
              sub={anchor?.n ? `${fmtNum(anchor.n_hit)}/${fmtNum(anchor.n)}` : undefined} />
        <Stat label="第6章快照" value={fmtNum(ch6.metrics?.snapshot_count ?? null)}
              sub={ch6.available ? '已评分样本如实统计' : '评估文件缺失'} />
        <Stat label="前向命中率" value={fmtNum(
          typeof ch6.metrics?.prediction_hit_rate === 'number'
            ? `${(ch6.metrics.prediction_hit_rate * 100).toFixed(1)}%`
            : null,
        )} sub={ch6.metrics?.prediction_scored != null
          ? `${fmtNum(ch6.metrics.prediction_scored)}/${fmtNum(ch6.metrics.prediction_count)} 已评分`
          : undefined} />
        <Stat label="对照算法" value={fmtNum(allFindings.length)} sub="1 modest / 2 负向" />
      </div>

      <Card title="三算法对照实验证据">
        {allFindings.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-body">
              <caption className="sr-only">三个算法改进方向与基线的对照实验结果，含诚实结论标注</caption>
              <thead>
                <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                  <th scope="col" className="text-left py-2 pr-3 font-normal">方向</th>
                  <th scope="col" className="text-left py-2 pr-3 font-normal">结论</th>
                  <th scope="col" className="text-right py-2 pr-3 font-normal">方向命中</th>
                  <th scope="col" className="text-right py-2 pr-3 font-normal">基线</th>
                  <th scope="col" className="text-right py-2 pr-3 font-normal">IC / ICIR</th>
                  <th scope="col" className="text-left py-2 font-normal">依据</th>
                </tr>
              </thead>
              <tbody className="text-sf-ink-2">
                {allFindings.map((f, i) => <FindingRow key={`${f.title ?? i}`} f={f} />)}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-body text-sf-ink-3">无可用对照实验数据，未做任何填充。</p>
        )}
        <p className="mt-2 text-label text-sf-ink-3">
          负向结果如实保留作方法学边界证据，不进生产决策链；「结论」列为实验判定，非买卖建议。
        </p>
      </Card>

      <Card title="SHAP 加性归因（可解释融合）">
        {shap.available ? (
          <div className="flow">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Stat label="基准仓位" value={fmtNum(shap.baseline)} sub="市场温度基准" />
              <Stat label="因子调节合计" value={fmtNum(shap.adjustments_total)} sub="Σ 各因子 φi" />
              <Stat label="最终仓位" value={fmtNum(shap.final_running)} sub={shap.as_of ? `数据日 ${shap.as_of}` : undefined} />
            </div>
            {Object.keys(shap.adjustments ?? {}).length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-body">
                  <caption className="sr-only">SHAP 式因子归因明细，按贡献绝对值排序</caption>
                  <thead>
                    <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                      <th scope="col" className="text-left py-2 pr-3 font-normal">因子</th>
                      <th scope="col" className="text-right py-2 font-normal">仓位贡献 (pt)</th>
                    </tr>
                  </thead>
                  <tbody className="text-sf-ink-2">
                    {Object.entries(shap.adjustments ?? {}).map(([k, v]) => (
                      <tr key={k} className="border-b border-sf-line last:border-0 hover:bg-sf-surface-2">
                        <td className="py-1.5 pr-3">{k}</td>
                        <td className="py-1.5 text-right tabular-nums">{fmtNum(v)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <p className="text-label text-sf-ink-3">
              归因基于决策闭环单一真理源 derive_position 的 contributions，加性可验：基准 + Σ调节 = 最终。
            </p>
          </div>
        ) : (
          <p className="text-body text-sf-ink-3">
            归因不可用：{fmtNum(shap.reason)}（未做任何填充）
          </p>
        )}
      </Card>

      <Card title="组合级非对称发现">
        {findings.asymmetric_finding ? (
          <div className="flow">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Stat label="防守侧累计" value={fmtNum(findings.asymmetric_finding.defensive_total_pp)} sub="百分点" />
              <Stat label="进攻侧累计" value={fmtNum(findings.asymmetric_finding.offensive_total_pp)} sub="百分点" />
              <Stat label="进攻年化代价" value={fmtNum(findings.asymmetric_finding.annualized_offensive_cost_pp)} sub="百分点/年" />
            </div>
            <p className="text-body text-sf-ink-2">{findings.asymmetric_finding.note}</p>
            {findings.asymmetric_finding.provenance && (
              <p className="text-label text-sf-ink-3">来源：{findings.asymmetric_finding.provenance}</p>
            )}
          </div>
        ) : (
          <p className="text-body text-sf-ink-3">无可用非对称发现数据，未做任何填充。</p>
        )}
      </Card>

      <Card title="第6章评估口径">
        {ch6.available && ch6.metrics ? (
          <div className="flow">
            <div className="flex flex-wrap gap-x-8 gap-y-2 text-body">
              <span>快照数 {fmtNum(ch6.metrics.snapshot_count)}</span>
              <span>日期区间 {fmtNum((ch6.metrics.snapshot_date_range as unknown[] | undefined)?.join(' ~ '))}</span>
              <span>温度区间 {fmtNum((ch6.metrics.temperature_min_max as unknown[] | undefined)?.join(' ~ '))}</span>
              <span>仓位 clamp 5~95 {ch6.metrics.position_clamp_5_95_ok === true ? '通过' : fmtNum(ch6.metrics.position_clamp_5_95_ok)}</span>
            </div>
            {typeof ch6.metrics.note === 'string' && (
              <p className="text-label text-sf-ink-3">口径：{ch6.metrics.note}</p>
            )}
          </div>
        ) : (
          <p className="text-body text-sf-ink-3">{fmtNum(ch6.note)}（未做任何填充）</p>
        )}
      </Card>
    </div>
  )
}

function FindingRow({ f }: { f: ThesisFinding }) {
  const isNeg = f.verdict === 'negative'
  const verdictLabel = isNeg ? '负向' : f.verdict === 'modest_positive' ? '小幅占优' : fmtNum(f.verdict)
  return (
    <tr className="border-b border-sf-line last:border-0 hover:bg-sf-surface-2 align-top">
      <td className="py-2 pr-3">{fmtNum(f.title)}</td>
      <td className="py-2 pr-3">
        <span className="inline-flex items-center rounded-tile border border-sf-line px-1.5 py-0.5 text-label text-sf-ink-2">
          {verdictLabel}
        </span>
      </td>
      <td className="py-2 pr-3 text-right tabular-nums">
        {f.direction_hit != null ? `${(f.direction_hit * 100).toFixed(2)}%` : '—'}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums">
        {f.direction_hit_baseline != null ? `${(f.direction_hit_baseline * 100).toFixed(2)}%` : '—'}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums">
        {f.ic != null || f.icir != null ? `${fmtNum(f.ic)} / ${fmtNum(f.icir)}` : '—'}
      </td>
      <td className="py-2 text-label text-sf-ink-3">{fmtNum(f.provenance)}</td>
    </tr>
  )
}
