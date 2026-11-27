import { useEffect, useState, type FormEvent } from 'react'
import { Button } from '@/shared/ui/Button'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'
import { Select, Textarea } from '@/shared/ui/Field'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { getCurrentUser } from '@/lib/auth'
import {
  ALERT_TYPES,
  ALERT_TYPE_LABELS,
  CONDITION_LABELS,
  SEVERITY_LABELS,
  CreatePriceAlertInputSchema,
  type AlertType,
  type PriceAlert,
  type MarketSeverity,
} from '@/api/schemas/alertWrite'
import {
  usePriceAlerts,
  useMarketAlerts,
  useMarketAlertConfig,
  useCreatePriceAlert,
  useTogglePriceAlert,
  useDeletePriceAlert,
  useMarkMarketAlertRead,
  useMarkAllMarketAlertsRead,
  useScanMarketAlerts,
  useUpdateMarketAlertConfig,
} from '@/lib/queriesAlertWrite'

/**
 * 可写预警面板（v1→v2 能力对齐批次）。
 *
 * 两块：
 *  1) 我的价格预警：四类 alert_type 选择 + 按类型必填输入 + 选股 + 列表/切换/删除；
 *  2) 市场指标异动提醒：severity 文字标签 + 分色（颜色非唯一信息）、未读数、
 *     单条/全部已读；管理员才显示「立即扫描」与配置查看/更新。
 *
 * 诚实红线：
 *  - 四态（loading/error/empty/data）由 QueryState 统一分发；
 *  - 写失败如实显示后端/网络错误，禁止把失败显示成成功、禁止乐观更新
 *    （统一工厂成功后 invalidateQueries 让服务端重新取数）；
 *  - null 值显示「—」，不 `?? 0` / `|| 0` / `new Date()` 兜底；
 *  - 管理员操作按 getCurrentUser().role === 'admin' 门控，非管理员不渲染按钮。
 */

/** severity 颜色只作辅助，文字标签（SEVERITY_LABELS）才是主信息载体。 */
const SEVERITY_CLASS: Record<MarketSeverity, string> = {
  info: 'border-sf-line text-sf-ink-2',
  warning: 'border-sf-warn text-sf-warn',
  danger: 'border-sf-danger text-sf-danger',
}

function firstErrorMessage(errors: unknown[]): string | null {
  for (const e of errors) {
    if (e instanceof Error) return e.message
  }
  return null
}

function ErrorText({ message }: { message: string }) {
  return (
    <p role="alert" className="my-2 rounded-tile border border-sf-line bg-sf-surface px-3 py-2 text-label text-sf-danger">
      操作失败：{message}
    </p>
  )
}

/** 非 price 类型的 params 是 JSON 文本，解析后给出可读描述（解析失败如实标注）。 */
function describeAlert(a: PriceAlert): string {
  if (a.alert_type === 'price') {
    return `${CONDITION_LABELS[a.condition]} 目标价 ${a.target_price}`
  }
  if (a.params === null) return '参数缺失'
  try {
    const parsed: unknown = JSON.parse(a.params)
    if (parsed !== null && typeof parsed === 'object') {
      const o = parsed as Record<string, unknown>
      if ('pattern_name' in o) return `形态：${String(o.pattern_name)}`
      if ('volume_ratio' in o) return `量比：${String(o.volume_ratio)}`
      if ('keyword' in o) return `关键词：${String(o.keyword)}`
    }
  } catch {
    return '参数不可解析'
  }
  return '参数未知'
}

const inputCls =
  'mt-1 w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent'
const labelCls = 'block text-label text-sf-ink-3'

function PriceAlertPanel() {
  const listQ = usePriceAlerts()
  const createM = useCreatePriceAlert()
  const toggleM = useTogglePriceAlert()
  const deleteM = useDeletePriceAlert()

  const [alertType, setAlertType] = useState<AlertType>('price')
  const [stockCode, setStockCode] = useState('')
  const [stockName, setStockName] = useState('')
  const [targetPrice, setTargetPrice] = useState('')
  const [condition, setCondition] = useState<'above' | 'below'>('above')
  const [patternName, setPatternName] = useState('')
  const [volumeRatio, setVolumeRatio] = useState('')
  const [keyword, setKeyword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  // 危险操作就地二次确认：首次点击只置确认态，不改数据。
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null)

  function buildRaw(): unknown {
    const base: Record<string, unknown> = { stock_code: stockCode.trim() }
    if (stockName.trim().length > 0) base.stock_name = stockName.trim()
    if (alertType === 'price') {
      return { ...base, alert_type: 'price', condition, target_price: Number(targetPrice) }
    }
    if (alertType === 'pattern') {
      return { ...base, alert_type: 'pattern', params: { pattern_name: patternName.trim() } }
    }
    if (alertType === 'volume') {
      return { ...base, alert_type: 'volume', params: { volume_ratio: Number(volumeRatio) } }
    }
    return { ...base, alert_type: 'announcement', params: { keyword: keyword.trim() } }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    createM.reset()
    // 客户端按与后端一致的规则做 discriminatedUnion 校验：缺必填参数不发请求、如实报错。
    const parsed = CreatePriceAlertInputSchema.safeParse(buildRaw())
    if (!parsed.success) {
      const first = parsed.error.issues[0]
      setFormError(first ? first.message : '参数不合法')
      return
    }
    createM.mutate(parsed.data, {
      onSuccess: () => {
        setStockCode('')
        setStockName('')
        setTargetPrice('')
        setPatternName('')
        setVolumeRatio('')
        setKeyword('')
      },
    })
  }

  const priceError = firstErrorMessage([createM.error, toggleM.error, deleteM.error])

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Select
            label="预警类型"
            value={alertType}
            onChange={(e) => setAlertType(e.target.value as AlertType)}
          >
            {ALERT_TYPES.map((t) => (
              <option key={t} value={t}>
                {ALERT_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>
          <StockSearchInput
            value={stockCode}
            label="选择股票"
            onSelect={(code, item) => {
              setStockCode(code)
              setStockName(item ? item.name : '')
            }}
          />
        </div>

        {alertType === 'price' && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className={labelCls}>
              目标价
              <input
                type="number"
                step="any"
                value={targetPrice}
                onChange={(e) => setTargetPrice(e.target.value)}
                placeholder="须大于 0，如 1850.5"
                className={inputCls}
              />
            </label>
            <Select
              label="预警方向"
              value={condition}
              onChange={(e) => setCondition(e.target.value as 'above' | 'below')}
            >
              <option value="above">上破</option>
              <option value="below">下破</option>
            </Select>
          </div>
        )}
        {alertType === 'pattern' && (
          <label className={labelCls}>
            形态名称
            <input
              value={patternName}
              onChange={(e) => setPatternName(e.target.value)}
              placeholder="如 早晨之星"
              className={inputCls}
            />
          </label>
        )}
        {alertType === 'volume' && (
          <label className={labelCls}>
            量比倍数
            <input
              type="number"
              step="any"
              value={volumeRatio}
              onChange={(e) => setVolumeRatio(e.target.value)}
              placeholder="须大于 0，如 2.5"
              className={inputCls}
            />
          </label>
        )}
        {alertType === 'announcement' && (
          <label className={labelCls}>
            公告关键词
            <input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="如 减持"
              className={inputCls}
            />
          </label>
        )}

        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" size="sm" disabled={createM.isPending}>
            {createM.isPending ? '创建中…' : '创建预警'}
          </Button>
          {stockCode && <span className="text-label text-sf-ink-3">已选代码：{stockCode}</span>}
        </div>
        {formError && <ErrorText message={formError} />}
        {priceError && <ErrorText message={priceError} />}
      </form>

      <QueryState
        isLoading={listQ.isLoading}
        isError={listQ.isError}
        error={listQ.error}
        isEmpty={listQ.data !== undefined && listQ.data.length === 0}
        emptyLabel="暂无价格预警"
        emptyHint="在上方按类型填写并创建一条预警后，会出现在这里"
      >
        <ul className="space-y-2">
          {listQ.data?.map((a) => (
            <li key={a.id} className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body">
                <span className="font-medium text-sf-ink">{a.stock_code}</span>
                {a.stock_name && <span className="text-sf-ink-2">{a.stock_name}</span>}
                <span className="rounded border border-sf-line px-1 text-label text-sf-ink-3">
                  {ALERT_TYPE_LABELS[a.alert_type]}
                </span>
                <span className="text-label text-sf-ink-2">{describeAlert(a)}</span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-label text-sf-ink-3">
                <span>创建时间：{a.created_at === null ? '—' : a.created_at}</span>
                <span>{a.triggered ? '已触发' : '未触发'}</span>
                <span>{a.active ? '启用中' : '已停用'}</span>
              </div>
              <div className="mt-2 flex gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  aria-label={`${a.active ? '停用' : '启用'}预警 ${a.id}`}
                  onClick={() => toggleM.mutate({ id: a.id })}
                >
                  {a.active ? '停用' : '启用'}
                </Button>
                {confirmingDeleteId !== a.id ? (
                  <Button
                    type="button"
                    variant="danger"
                    size="sm"
                    aria-label={`删除预警 ${a.id}`}
                    onClick={() => setConfirmingDeleteId(a.id)}
                  >
                    删除
                  </Button>
                ) : (
                  <>
                    <span className="text-label text-sf-ink-2">确认删除该条预警？删除后不可恢复</span>
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      disabled={deleteM.isPending}
                      onClick={() => deleteM.mutate({ id: a.id })}
                    >
                      {deleteM.isPending ? '删除中…' : '确认删除'}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmingDeleteId(null)}
                    >
                      取消
                    </Button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      </QueryState>
    </div>
  )
}

function MarketAlertPanel() {
  const admin = getCurrentUser()?.role === 'admin'
  const [unreadOnly, setUnreadOnly] = useState(false)
  const listQ = useMarketAlerts(unreadOnly ? { unread_only: true } : undefined)
  const readM = useMarkMarketAlertRead()
  const readAllM = useMarkAllMarketAlertsRead()
  const scanM = useScanMarketAlerts()
  const configQ = useMarketAlertConfig(admin)
  const updateConfigM = useUpdateMarketAlertConfig()
  const [configText, setConfigText] = useState('')
  const [configError, setConfigError] = useState<string | null>(null)

  useEffect(() => {
    if (configQ.data) setConfigText(JSON.stringify(configQ.data.config, null, 2))
  }, [configQ.data])

  function handleUpdateConfig() {
    setConfigError(null)
    updateConfigM.reset()
    let parsed: Record<string, unknown>
    try {
      const v: unknown = JSON.parse(configText)
      if (v === null || typeof v !== 'object' || Array.isArray(v)) {
        throw new Error('配置须为 JSON 对象')
      }
      parsed = v as Record<string, unknown>
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : '配置格式错误')
      return
    }
    updateConfigM.mutate({ config: parsed })
  }

  const marketError = firstErrorMessage([readM.error, readAllM.error, scanM.error, updateConfigM.error])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {listQ.data && (
          <span className="rounded-tile border border-sf-line px-2 py-1 text-label text-sf-ink-2">
            未读 {listQ.data.unread_count} 条 / 共 {listQ.data.total} 条
          </span>
        )}
        <label className="flex items-center gap-1 text-label text-sf-ink-3">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
          />
          仅看未读
        </label>
        <Button type="button" variant="secondary" size="sm" disabled={readAllM.isPending} onClick={() => readAllM.mutate()}>
          {readAllM.isPending ? '处理中…' : '全部标记已读'}
        </Button>
      </div>

      {admin && (
        <div className="space-y-2 rounded-tile border border-sf-line p-3">
          <div className="flex items-center gap-3">
            <Button type="button" variant="secondary" size="sm" disabled={scanM.isPending} onClick={() => scanM.mutate()}>
              {scanM.isPending ? '扫描中…' : '立即扫描'}
            </Button>
            {scanM.isSuccess && scanM.data && (
              <span className="text-label text-sf-ink-2">本次新增 {scanM.data.inserted} 条</span>
            )}
          </div>
          <div className="text-label text-sf-ink-3">扫描策略配置（管理员）</div>
          <QueryState
            isLoading={configQ.isLoading}
            isError={configQ.isError}
            error={configQ.error}
            isEmpty={!configQ.data}
            emptyLabel="配置不可得"
          >
            <div className="space-y-2">
              <Textarea
                label="扫描策略配置"
                value={configText}
                onChange={(e) => setConfigText(e.target.value)}
                rows={6}
                className="[&_textarea]:font-mono"
              />
              <Button type="button" variant="primary" size="sm" disabled={updateConfigM.isPending} onClick={handleUpdateConfig}>
                {updateConfigM.isPending ? '保存中…' : '保存配置'}
              </Button>
              {configQ.data && (
                <pre className="whitespace-pre-wrap text-label text-sf-ink-3">
                  runtime_overrides：{JSON.stringify(configQ.data.runtime_overrides)}
                </pre>
              )}
            </div>
          </QueryState>
        </div>
      )}
      {configError && <ErrorText message={configError} />}
      {marketError && <ErrorText message={marketError} />}

      <QueryState
        isLoading={listQ.isLoading}
        isError={listQ.isError}
        error={listQ.error}
        isEmpty={listQ.data !== undefined && listQ.data.items.length === 0}
        emptyLabel={unreadOnly ? '没有未读提醒' : '暂无市场异动提醒'}
      >
        <ul className="space-y-2">
          {listQ.data?.items.map((m) => (
            <li key={m.id} className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className={`rounded border px-1.5 py-0.5 text-label ${SEVERITY_CLASS[m.severity]}`}>
                  {SEVERITY_LABELS[m.severity]}
                </span>
                <span className="font-medium text-sf-ink">{m.metric_name}</span>
                <span className="font-mono text-label text-sf-ink-3">{m.metric_key}</span>
              </div>
              <p className="mt-1 text-body text-sf-ink-2">{m.message}</p>
              <div className="mt-1 flex flex-wrap gap-x-3 text-label text-sf-ink-3">
                <span>数值：{m.value === null ? '—' : m.value}</span>
                <span>阈值：{m.threshold === null ? '—' : m.threshold}</span>
                <span>时间：{m.created_at === null ? '—' : m.created_at}</span>
              </div>
              <div className="mt-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  aria-label={`标记已读 ${m.id}`}
                  disabled={readM.isPending}
                  onClick={() => readM.mutate({ id: m.id })}
                >
                  {readM.isPending ? '处理中…' : '标记已读'}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </QueryState>
    </div>
  )
}

export function AlertWritePanels() {
  return (
    <div className="space-y-4">
      <Card title="我的价格预警（可写 · 按登录用户隔离）">
        <PriceAlertPanel />
      </Card>
      <Card title="市场指标异动提醒">
        <MarketAlertPanel />
      </Card>
    </div>
  )
}
