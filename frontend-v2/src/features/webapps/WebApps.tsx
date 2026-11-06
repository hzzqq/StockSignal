import { useWebApps } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'

/** 86 网页作品集：列出 webapps 下各 meta.json 中的作品，点击在新标签打开 entry。 */
export function WebApps() {
  const q = useWebApps()

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">网页作品集</h2>
      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
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
              className="block rounded-xl bg-sf-card border border-sf-border p-4 hover:border-ss-up/50 transition"
            >
              <div className="font-medium">{w.title}</div>
              <div className="text-xs text-sf-txt/50 mt-1 line-clamp-2">{w.desc ?? ''}</div>
              <div className="text-xs text-sf-txt/40 mt-2">
                v{w.version ?? '—'} · {w.added ?? '—'}
              </div>
            </a>
          ))}
        </div>
      </QueryState>
    </div>
  )
}
