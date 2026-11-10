import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { V1_PAGES, V1_PAGE_GROUPS, V1_PAGES_TOTAL, type V1Page } from './v1Pages.generated'
import { mappingOf, statusCounts, type V2Status } from './v2Mapping'
import { v1PageUrl } from '@/lib/preferences'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'

/**
 * v1 功能全景（/catalog）：把 v1 的**全部**功能页纳入 v2 的可发现入口。
 *
 * 诚实红线（重要）：列出全部 v1 页 ≠ v2 已实现全部功能。三档状态如实标注：
 *   ✅ 已实现 → 直达等价 v2 路由；
 *   🔗 关联数据 → v2 无等价页面，只能查看真实只读端点的数据（不等同功能）；
 *   ⏳ 仅 v1 → v2 尚未迁移，明确说明并给出 v1 直达链接。
 * 清单来自 scripts/gen_v1_pages.py 实时扫描磁盘，不由前端手抄，数量也不写死。
 */

const STATUS_META: Record<V2Status, { label: string; cls: string; hint: string }> = {
  native: { label: '已实现', cls: 'text-sf-ok', hint: 'v2 有等价页面' },
  data: { label: '关联数据', cls: 'text-sf-accent', hint: '仅查看关联只读数据，非等价功能' },
  'v1-only': { label: '待迁移', cls: 'text-sf-ink-3', hint: 'v2 尚未迁移，计划迁移' },
  'v1-pinned': { label: 'v1 保留', cls: 'text-sf-ink-2', hint: 'v2 不做等价实现，永久留 v1' },
}

type Filter = 'all' | V2Status

function PageRow({ page }: { page: V1Page }) {
  const m = mappingOf(page)
  const meta = STATUS_META[m.status]
  return (
    <li className="flex flex-wrap items-center gap-2 border-b border-sf-line last:border-0 py-2">
      <span className="w-8 shrink-0 text-label tabular-nums text-sf-ink-3">{page.num}</span>
      <span className="min-w-[9rem] flex-1 text-body text-sf-ink">{page.name}</span>
      <span className={`text-label ${meta.cls}`} title={meta.hint}>{meta.label}</span>
      <span className="w-full text-label text-sf-ink-3 sm:w-auto sm:flex-1">
        {m.status === 'native' ? m.note ?? '直达 v2 等价页面'
          : m.status === 'data' ? `关联：${m.dataLabel ?? '只读端点'}`
            : m.status === 'v1-pinned' ? (m.note ?? 'v2 不做等价实现，永久留 v1')
              : 'v2 尚未迁移，需从 v1 打开'}
      </span>
      <span className="shrink-0">
        {m.status === 'native' && m.to ? (
          <Link to={m.to} className="text-label text-sf-accent hover:underline">打开 v2 →</Link>
        ) : m.status === 'data' && m.dataPath ? (
          <Link to="/data" search={{ path: m.dataPath }} className="text-label text-sf-accent hover:underline">
            查看数据 →
          </Link>
        ) : (
          <a
            href={v1PageUrl(page.v1Url)}
            target="_blank"
            rel="noreferrer"
            className="text-label text-sf-accent hover:underline"
          >
            在 v1 打开 ↗
          </a>
        )}
      </span>
    </li>
  )
}

export function CatalogView() {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const counts = statusCounts()

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    return V1_PAGE_GROUPS.map((group) => ({
      group,
      pages: V1_PAGES.filter((p) => {
        if (p.group !== group) return false
        if (filter !== 'all' && mappingOf(p).status !== filter) return false
        if (q && !`${p.name} ${p.file} ${p.num}`.toLowerCase().includes(q)) return false
        return true
      }),
    })).filter((g) => g.pages.length > 0)
  }, [query, filter])

  const shown = groups.reduce((n, g) => n + g.pages.length, 0)

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">v1 功能全景</h2>
        <Link to="/settings" className="text-body text-sf-accent hover:underline">设置 v1 地址 →</Link>
      </div>

      <p className="text-label text-sf-ink-3">
        本页列出 v1 全部 {V1_PAGES_TOTAL} 个功能页，清单由 <code className="font-mono">scripts/gen_v1_pages.py</code> 扫描
        <code className="font-mono"> pages/*.py </code>生成（非手写），并有漂移守卫逐项核对。
        <strong>列出 ≠ 已实现</strong>：「关联数据」只是查看真实只读端点，不等同于该功能；「待迁移」表示 v2 尚未迁移；「v1 保留」表示 v2 明确不做等价实现（如实盘交易等真实下单能力）。
      </p>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="v1 功能页总数" value={V1_PAGES_TOTAL} sub="磁盘实扫" />
        <Stat label="v2 已实现" value={counts.native} sub="可直达等价页面" />
        <Stat label="关联只读数据" value={counts.data} sub="非等价功能" />
        <Stat label="v1 保留" value={counts['v1-pinned']} sub="永久不迁 v2" />
        <Stat label="待迁移" value={counts['v1-only']} sub="如实标注，不造空壳页" />
      </div>

      <Card title="筛选">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex flex-col gap-1 text-label text-sf-ink-2">
            搜索功能
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="名称 / 文件名 / 编号"
              aria-label="搜索功能"
              className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
            />
          </label>
          <div role="group" aria-label="状态筛选" className="flex items-center gap-1">
            {(['all', 'native', 'data', 'v1-pinned', 'v1-only'] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                aria-pressed={filter === f}
                className={[
                  'px-2 py-1.5 rounded-tile text-label border transition-colors',
                  filter === f ? 'text-sf-ink border-sf-accent bg-sf-surface-2' : 'text-sf-ink-2 border-sf-line',
                ].join(' ')}
              >
                {f === 'all' ? '全部' : STATUS_META[f].label}
              </button>
            ))}
          </div>
          <span className="text-label text-sf-ink-3">当前显示 {shown} 项</span>
        </div>
      </Card>

      {groups.length === 0 ? (
        <Card><p className="text-body text-sf-ink-3">没有匹配的功能页。</p></Card>
      ) : groups.map((g) => (
        <Card key={g.group} title={`${g.group}（${g.pages.length}）`}>
          <ul className="m-0 list-none p-0">
            {g.pages.map((p) => <PageRow key={p.file} page={p} />)}
          </ul>
        </Card>
      ))}

      <p className="text-label text-sf-ink-3">
        v1 直达链接的地址可在「设置」里修改（默认 http://127.0.0.1:8501，需 v1 服务正在运行）。
      </p>
    </div>
  )
}
