import { useWebApps } from '@/lib/queries'
import { ErrorState, QueryState } from '@/shared/ui/States'

/** 86 网页作品集：列出 webapps 下各 meta.json 中的作品，点击在新标签打开 entry。 */
function isBackendUnavailable(err: unknown): boolean {
  if (!(err instanceof Error)) return false
  return /502|504|Bad Gateway|空响应|Failed to fetch|NetworkError/i.test(err.message)
}

export function WebApps() {
  const q = useWebApps()
  const errMsg = q.error instanceof Error ? q.error.message : '作品集清单加载失败'

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">网页作品集</h2>

      {q.isError ? (
        <>
          <ErrorState message={errMsg} />
          <div
            role="alert"
            className="rounded-tile border border-sf-line bg-sf-surface px-4 py-3 text-body text-sf-ink-2"
          >
            <p>
              {isBackendUnavailable(q.error)
                ? '后端服务可能正在重启或未启动（Flask 5050）。确认服务已运行后重试；不会用假数据填充清单。'
                : '清单读取失败。请查看错误原文后重试；不会用假数据填充清单。'}
            </p>
            <button
              type="button"
              onClick={() => void q.refetch()}
              disabled={q.isFetching}
              className="mt-3 rounded-tile border border-sf-line px-3 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-60"
            >
              {q.isFetching ? '重试中…' : '重新加载作品清单'}
            </button>
            {q.data?.length ? (
              <p className="mt-2 text-label text-sf-ink-3">当前显示的是上一次成功获取的清单，非本次结果。</p>
            ) : null}
          </div>
        </>
      ) : (
        <QueryState
          isLoading={q.isLoading}
          isError={false}
          isEmpty={!q.data || q.data.length === 0}
          emptyLabel="暂无作品"
          emptyHint="webapps/*/meta.json 未找到"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {q.data?.map((w) => (
              <a
                key={w.dir}
                href={`/webapps/${w.dir}/${w.entry}`}
                target="_blank"
                rel="noreferrer"
                className="block rounded-card bg-sf-surface border border-sf-line p-4 hover:border-sf-accent transition-colors"
              >
                <div className="font-medium">{w.title}</div>
                <div className="text-xs text-sf-ink-3 mt-1 line-clamp-2">{w.desc ?? ''}</div>
                <div className="text-xs text-sf-ink-3 mt-2">
                  v{w.version ?? '—'} · {w.added ?? '—'}
                </div>
              </a>
            ))}
          </div>
        </QueryState>
      )}
    </div>
  )
}
