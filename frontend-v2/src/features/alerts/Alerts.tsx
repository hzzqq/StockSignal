import { useAlertRules, useAlertLog } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'
import { SectionTitle } from '@/shared/ui/EmphasisText'
// v1 47 价格预警 / 94 市场异动提醒的写能力（后端早有 REST 端点，v2 此前整批悬空）。
import { AlertWritePanels } from './AlertWritePanels'

/** 74 告警引擎：展示告警规则与触发日志（当前数据文件缺失 → 诚实渲染「无数据」）。 */
export function Alerts() {
  const rulesQ = useAlertRules()
  const logQ = useAlertLog()

  return (
    <div className="space-y-4">
      <SectionTitle as="h2">告警引擎</SectionTitle>

      <Card title="告警规则（alert_rules.json）">
        <QueryState
          isLoading={rulesQ.isLoading}
          isError={rulesQ.isError}
          error={rulesQ.error}
          isEmpty={!rulesQ.data}
          emptyLabel="暂无告警规则"
          emptyHint="data/alert_rules.json 当前缺失"
        >
          {rulesQ.data && (
            <pre className="text-xs text-sf-ink-2 whitespace-pre-wrap">
              {JSON.stringify(rulesQ.data, null, 2)}
            </pre>
          )}
        </QueryState>
      </Card>

      <Card title="告警日志（alerts.log）">
        <QueryState
          isLoading={logQ.isLoading}
          isError={logQ.isError}
          error={logQ.error}
          isEmpty={!logQ.data}
          emptyLabel="暂无告警日志"
          emptyHint="data/alerts.log 当前缺失"
        >
          {logQ.data && (
            <pre className="text-xs text-sf-ink-2 whitespace-pre-wrap max-h-72 overflow-auto">
              {logQ.data}
            </pre>
          )}
        </QueryState>
      </Card>

      <AlertWritePanels />
    </div>
  )
}
