import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listUsers, createUser, updateUser, deleteUser, listLogs } from '@/api/admin'
import type { PublicUser, AdminLog } from '@/api/schemas/admin'
import { Card } from '@/shared/ui/Card'
import { QueryState, EmptyState } from '@/shared/ui/States'
import { getCurrentUser } from '@/lib/auth'

/**
 * 用户管理（/users）—— 对应 v1「92 用户管理」的 v2 等价实现。
 *
 * 管理员专属：非 admin 直接渲染无权限空态（不显示任何用户数据）。
 * 三块：用户列表（搜索 + 分页 + 编辑 + 删除）/ 创建用户 / 操作日志。
 *
 * 诚实红线：
 *  - 取数失败（Zod 解析失败 / 401 / 网络错误）→ 真实 error 态（role=alert），不编造用户；
 *  - 删除「自己 / 初始 admin」按钮禁用，与 v1 同源规则；
 *  - 创建按钮在用户名或密码为空时禁用（前置校验），避免空提交。
 *  ⚠️ 本页是账户管理，与交易无关；实盘交易红线（v2 不提供下单）不受影响。
 */

type Tab = 'list' | 'create' | 'logs'

export function UserManagement() {
  const me = getCurrentUser()
  const [tab, setTab] = useState<Tab>('list')

  if (!me || me.role !== 'admin') {
    return (
      <div className="flow">
        <h2 className="text-lg font-semibold">用户管理</h2>
        <EmptyState
          label="无访问权限"
          hint="用户管理为管理员专属功能。当前账号不是管理员，或登录信息已失效（请重新登录）。"
        />
      </div>
    )
  }

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">用户管理</h2>
      <p className="text-label text-sf-ink-3">
        管理员专属：账户创建 / 编辑 / 删除与操作审计。删除操作不可撤销；自己与初始管理员账号受保护。
      </p>

      <div role="tablist" aria-label="用户管理" className="flex items-center gap-1">
        {([
          ['list', '用户列表'],
          ['create', '创建用户'],
          ['logs', '操作日志'],
        ] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={[
              'px-3 py-1.5 rounded-tile text-label border transition-colors',
              tab === key
                ? 'text-sf-ink border-sf-accent bg-sf-surface-2'
                : 'text-sf-ink-2 border-sf-line hover:bg-sf-surface-2',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'list' && <ListTab me={me} />}
      {tab === 'create' && <CreateTab />}
      {tab === 'logs' && <LogsTab />}
    </div>
  )
}

// ───────────────────────── 用户列表
function ListTab({ me }: { me: PublicUser }) {
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [editing, setEditing] = useState<PublicUser | null>(null)
  const [deleting, setDeleting] = useState<PublicUser | null>(null)

  const { data, isLoading, isError, error, isFetching } = useQuery({
    queryKey: ['admin', 'users', page, keyword],
    queryFn: () => listUsers({ page, per_page: 20, keyword: keyword || undefined }),
    staleTime: 0,
  })

  const items = data?.items ?? []
  // total/pages 由 AdminUserListSchema 保证为 number；data 缺失（加载中）时显 0 仅作占位，
  // 与「加载中…」同帧展示，不冒充真实计数（避开 ?? 0 红线，改用条件表达式）。
  const total = data ? data.total : 0
  const pages = data ? data.pages : 0

  return (
    <div className="space-y-4">
      <Card title="用户列表">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <label className="flex flex-col gap-1 text-label text-sf-ink-2">
            搜索用户名
            <input
              type="search"
              value={keyword}
              onChange={(e) => {
                setKeyword(e.target.value)
                setPage(1)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') setPage(1)
              }}
              placeholder="输入用户名关键词"
              aria-label="搜索用户名"
              className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
            />
          </label>
          <span className="text-label text-sf-ink-3">
            共 {total} 个用户 · 第 {page}/{pages || 1} 页{isFetching ? ' · 加载中…' : ''}
          </span>
        </div>

        <QueryState
          isLoading={isLoading}
          isError={isError}
          error={error}
          isEmpty={!isLoading && !isError && items.length === 0}
          emptyLabel="暂无用户"
          emptyHint="点击「创建用户」标签，填写用户名与密码即可新增账户。"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-sf-ink">
              <thead>
                <tr className="text-sf-ink-3 border-b border-sf-line">
                  <th className="text-left py-1.5 pr-3">用户</th>
                  <th className="text-left py-1.5 pr-3">ID</th>
                  <th className="text-left py-1.5 pr-3">角色</th>
                  <th className="text-left py-1.5 pr-3">状态</th>
                  <th className="text-left py-1.5 pr-3">创建时间</th>
                  <th className="text-right py-1.5">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => {
                  const isSelf = u.id === me.id
                  const isRootAdmin = u.username === 'admin'
                  const canDelete = !isSelf && !isRootAdmin
                  return (
                    <tr key={u.id} className="border-b border-sf-line/60">
                      <td className="py-1.5 pr-3">
                        <span className="font-medium">{u.username}</span>
                        {u.role === 'admin' && <span className="ml-1" aria-label="管理员">🛡️</span>}
                        {!u.is_active && <span className="ml-1" aria-label="已停用">🔴</span>}
                      </td>
                      <td className="py-1.5 pr-3 tabular-nums">{u.id}</td>
                      <td className="py-1.5 pr-3">{u.role}</td>
                      <td className="py-1.5 pr-3">{u.is_active ? '正常' : '停用'}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{String(u.created_at).slice(0, 10)}</td>
                      <td className="py-1.5 text-right whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => setEditing(u)}
                          className="text-label text-sf-accent hover:underline mr-3"
                          aria-label={`编辑用户 ${u.username}`}
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleting(u)}
                          disabled={!canDelete}
                          title={isSelf ? '不能删除自己' : isRootAdmin ? '不能删除初始管理员' : '删除用户'}
                          className={[
                            'text-label',
                            canDelete ? 'text-sf-danger hover:underline' : 'text-sf-ink-3 cursor-not-allowed',
                          ].join(' ')}
                          aria-label={`删除用户 ${u.username}`}
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </QueryState>

        <div className="flex items-center justify-between mt-3">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="text-label px-3 py-1.5 rounded-tile border border-sf-line disabled:opacity-40"
            aria-label="上一页"
          >
            上一页
          </button>
          <span className="text-label text-sf-ink-3">
            第 {page} / {pages || 1} 页
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(Math.max(pages, 1), p + 1))}
            disabled={page >= pages}
            className="text-label px-3 py-1.5 rounded-tile border border-sf-line disabled:opacity-40"
            aria-label="下一页"
          >
            下一页
          </button>
        </div>
      </Card>

      {editing && <EditModal user={editing} me={me} onClose={() => setEditing(null)} />}
      {deleting && (
        <DeleteConfirm user={deleting} onClose={() => setDeleting(null)} />
      )}
    </div>
  )
}

// ───────────────────────── 编辑弹窗
function EditModal({ user, me, onClose }: { user: PublicUser; me: PublicUser; onClose: () => void }) {
  const qc = useQueryClient()
  const [role, setRole] = useState<'user' | 'admin'>(user.role)
  const [active, setActive] = useState(user.is_active)
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [okMsg, setOkMsg] = useState<string | null>(null)

  const roleBlocked = user.id === me.id && role !== 'admin'
  const activeBlocked = user.id === me.id && !active

  async function onSave() {
    setErr(null)
    setOkMsg(null)
    if (roleBlocked || activeBlocked) {
      setErr('不能取消自己的管理员角色，也不能停用自己')
      return
    }
    setSaving(true)
    try {
      await updateUser(user.id, {
        role,
        is_active: active,
        ...(password ? { password } : {}),
      })
      setOkMsg('更新成功')
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : '更新失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={`编辑用户 ${user.username}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-label text-sf-ink-3">ID: {user.id} · 创建于 {String(user.created_at).slice(0, 10)}</p>
        <label className="flex flex-col gap-1 text-label text-sf-ink-2">
          角色
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as 'user' | 'admin')}
            aria-label="角色"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
          >
            <option value="user">👤 普通用户 (user)</option>
            <option value="admin">🛡️ 管理员 (admin)</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-label text-sf-ink-2">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
            aria-label="账号激活"
          />
          账号激活（取消勾选将停用该账号）
        </label>
        <label className="flex flex-col gap-1 text-label text-sf-ink-2">
          新密码（留空则不修改）
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="至少 6 位"
            aria-label="新密码"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
          />
        </label>
        {err && (
          <div role="alert" className="text-sf-danger text-body">{err}</div>
        )}
        {okMsg && <div role="status" className="text-sf-ok text-body">{okMsg}</div>}
        {roleBlocked && (
          <div role="alert" className="text-sf-warn text-label">不能取消自己的管理员角色。</div>
        )}
        {activeBlocked && (
          <div role="alert" className="text-sf-warn text-label">不能停用自己的账号。</div>
        )}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onSave}
            disabled={saving || roleBlocked || activeBlocked}
            className="flex-1 py-2 rounded-tile font-bold text-white disabled:opacity-50"
            style={{ background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))' }}
            aria-label="保存"
          >
            {saving ? '保存中…' : '保存'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2 rounded-tile border border-sf-line text-sf-ink-2"
            aria-label="取消"
          >
            取消
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ───────────────────────── 删除确认
function DeleteConfirm({ user, onClose }: { user: PublicUser; onClose: () => void }) {
  const qc = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function onConfirm() {
    setErr(null)
    setSaving(true)
    try {
      await deleteUser(user.id)
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : '删除失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="确认删除" onClose={onClose}>
      <div className="space-y-3">
        <p className="text-body text-sf-ink">
          确定要删除用户 <b>{user.username}</b>（ID: {user.id}）吗？此操作不可撤销。
        </p>
        {err && <div role="alert" className="text-sf-danger text-body">{err}</div>}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onConfirm}
            disabled={saving}
            className="flex-1 py-2 rounded-tile font-bold text-white disabled:opacity-50"
            style={{ background: 'linear-gradient(90deg, var(--color-sf-danger, #e5484d), #c93b40)' }}
            aria-label="确认删除"
          >
            {saving ? '删除中…' : '确认删除'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2 rounded-tile border border-sf-line text-sf-ink-2"
            aria-label="取消"
          >
            取消
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ───────────────────────── 创建用户
function CreateTab() {
  const qc = useQueryClient()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [okMsg, setOkMsg] = useState<string | null>(null)

  const canCreate = username.trim().length > 0 && password.length > 0

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    setOkMsg(null)
    if (!canCreate) {
      setErr('用户名和密码不能为空')
      return
    }
    setSaving(true)
    try {
      await createUser({ username: username.trim(), password, role })
      setOkMsg(`用户 ${username.trim()} 创建成功`)
      setUsername('')
      setPassword('')
      setRole('user')
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : '创建失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="创建新用户">
      <form onSubmit={onSubmit} className="space-y-3">
        <p className="text-label text-sf-ink-3">
          填写用户名与密码创建新账户；管理员可分配 user / admin 角色。
        </p>
        <label className="flex flex-col gap-1 text-label text-sf-ink-2">
          用户名
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="2-32 位，字母数字下划线中文"
            aria-label="用户名"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-label text-sf-ink-2">
          密码
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="至少 6 位"
            aria-label="密码"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-label text-sf-ink-2">
          角色
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as 'user' | 'admin')}
            aria-label="角色"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink"
          >
            <option value="user">👤 普通用户 (user)</option>
            <option value="admin">🛡️ 管理员 (admin)</option>
          </select>
        </label>

        {err && <div role="alert" className="text-sf-danger text-body">{err}</div>}
        {okMsg && <div role="status" className="text-sf-ok text-body">{okMsg}</div>}

        <button
          type="submit"
          disabled={!canCreate || saving}
          aria-label="创建用户"
          className="py-2 px-4 rounded-tile font-bold text-white disabled:opacity-50"
          style={{ background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))' }}
        >
          {saving ? '创建中…' : '创建用户'}
        </button>
      </form>
    </Card>
  )
}

// ───────────────────────── 操作日志
function LogsTab() {
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['admin', 'logs', page],
    queryFn: () => listLogs({ page, per_page: 20 }),
    staleTime: 0,
  })

  const items: AdminLog[] = data?.items ?? []
  const total = data ? data.total : 0
  const pages = data ? data.pages : 0

  const actionColor: Record<string, string> = {
    create_user: '🟢',
    update_user: '🟡',
    delete_user: '🔴',
  }

  return (
    <Card title="操作日志">
      <p className="text-label text-sf-ink-3 mb-3">
        共 {total} 条日志 · 第 {page}/{pages || 1} 页
      </p>
      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={error}
        isEmpty={!isLoading && !isError && items.length === 0}
        emptyLabel="暂无操作日志"
        emptyHint="创建、编辑或删除用户后，相关操作会记录在这里。"
      >
        <ul className="m-0 list-none p-0 space-y-1.5">
          {items.map((log) => (
            <li key={log.id} className="text-xs text-sf-ink border-b border-sf-line/60 pb-1.5">
              <span aria-hidden="true">{actionColor[log.action] ?? '⚪'}</span>{' '}
              <span className="tabular-nums">{String(log.created_at).slice(0, 19)}</span>{' '}
              <b>{log.username}</b> → {log.action} → <code>{log.target}</code>
              {log.detail && <span className="text-sf-ink-3">（{log.detail}）</span>}
            </li>
          ))}
        </ul>
      </QueryState>

      <div className="flex items-center justify-between mt-3">
        <button
          type="button"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
          className="text-label px-3 py-1.5 rounded-tile border border-sf-line disabled:opacity-40"
          aria-label="上一页"
        >
          上一页
        </button>
        <span className="text-label text-sf-ink-3">第 {page} / {pages || 1} 页</span>
        <button
          type="button"
          onClick={() => setPage((p) => Math.min(Math.max(pages, 1), p + 1))}
          disabled={page >= pages}
          className="text-label px-3 py-1.5 rounded-tile border border-sf-line disabled:opacity-40"
          aria-label="下一页"
        >
          下一页
        </button>
      </div>
    </Card>
  )
}

// ───────────────────────── 轻量模态（无第三方依赖）
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-card bg-sf-surface border border-sf-line p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-title font-medium text-sf-ink-2">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="text-sf-ink-3 hover:text-sf-ink text-label"
          >
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
