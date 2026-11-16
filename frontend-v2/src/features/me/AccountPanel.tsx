import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Card } from '@/shared/ui/Card'
import { ErrorState, QueryState } from '@/shared/ui/States'
import { SettingsInputSchema, AvatarInputSchema } from '@/api/schemas/community'
import {
  useMe,
  useTokenInfo,
  useLoginHistory,
  useSaveSettings,
  useSaveAvatar,
  useLogout,
} from '@/lib/queriesCommunity'

/**
 * 账户面板（挂在 /me 下）：真实接后端 auth 写端点。
 *
 * 能力：token 信息（sub/role/iat/exp，iat/exp 如实标注「Unix 秒」）、登录历史、
 * 偏好设置编辑保存（JSON 对象，保存前校验合法 object）、头像上传（FileReader 转 data URL，
 * 校验 data:image/ 前缀与体积）、登出（成功后清 token 并跳 /login）。
 *
 * 诚实红线：四态齐全（加载/错误/空/有数据）、写失败显示真实错误文案、非法 JSON/非法头像
 * 在客户端如实拒绝（不伪装成保存成功）、登出只在真实成功后丢弃 token（不伪造成功）。
 */
export function AccountPanel() {
  const navigate = useNavigate()
  const meQ = useMe()
  const tokenQ = useTokenInfo()
  const loginsQ = useLoginHistory()
  const settingsM = useSaveSettings()
  const avatarM = useSaveAvatar()
  const logoutM = useLogout()

  const [settingsText, setSettingsText] = useState('')
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [avatarError, setAvatarError] = useState<string | null>(null)
  const initialized = useRef(false)

  // 首次拿到 /me 后把当前偏好回填到编辑框（只回填一次，保存后不被刷新覆盖用户输入）。
  useEffect(() => {
    if (!initialized.current && meQ.data) {
      setSettingsText(
        meQ.data.settings === undefined ? '{}' : JSON.stringify(meQ.data.settings, null, 2),
      )
      initialized.current = true
    }
  }, [meQ.data])

  const errMsg = (e: unknown): string => (e instanceof Error ? e.message : '操作失败')

  function submitSettings() {
    let obj: unknown
    try {
      obj = JSON.parse(settingsText)
    } catch {
      setSettingsError('设置内容不是合法 JSON')
      return
    }
    if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
      setSettingsError('settings 必须是对象')
      return
    }
    const parsed = SettingsInputSchema.safeParse({ settings: obj })
    if (!parsed.success) {
      setSettingsError(parsed.error.issues[0]?.message ?? 'settings 必须是对象')
      return
    }
    setSettingsError(null)
    settingsM.mutate({ settings: parsed.data.settings })
  }

  function onAvatarFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        setAvatarError('头像读取失败')
        return
      }
      const parsed = AvatarInputSchema.safeParse({ avatar: result })
      if (!parsed.success) {
        setAvatarError(parsed.error.issues[0]?.message ?? '头像不合法')
        return
      }
      setAvatarError(null)
      avatarM.mutate({ avatar: parsed.data.avatar })
    }
    reader.onerror = () => setAvatarError('头像读取失败')
    reader.readAsDataURL(file)
  }

  function submitLogout() {
    logoutM.logout(() => navigate({ to: '/login', search: { from: '/' } }))
  }

  return (
    <div className="space-y-4">
      <h3 className="text-title font-medium text-sf-ink-2">账户管理</h3>
      <p className="text-xs text-sf-ink-3">
        Token 声明 / 登录历史 / 偏好设置 / 头像 / 登出（演示态为 MSW 模拟响应，非真实后端数据）。
      </p>

      <Card title="当前账户">
        <QueryState
          isLoading={meQ.isLoading}
          isError={meQ.isError}
          error={meQ.error}
          emptyLabel="暂无账户信息"
        >
          {meQ.data && (
            <p className="text-body text-sf-ink">
              {meQ.data.username} · {meQ.data.role === 'admin' ? '管理员' : '普通用户'} · 账号 ID{' '}
              {meQ.data.id}
            </p>
          )}
        </QueryState>
      </Card>

      <Card title="Token 信息">
        <QueryState
          isLoading={tokenQ.isLoading}
          isError={tokenQ.isError}
          error={tokenQ.error}
          emptyLabel="暂无 Token 信息"
        >
          {tokenQ.data && (
            <dl className="grid grid-cols-2 gap-1 text-body text-sf-ink-2">
              <dt className="text-sf-ink-3">sub</dt>
              <dd className="text-sf-ink">{tokenQ.data.sub}</dd>
              <dt className="text-sf-ink-3">uid</dt>
              <dd className="text-sf-ink">{tokenQ.data.uid}</dd>
              <dt className="text-sf-ink-3">role</dt>
              <dd className="text-sf-ink">{tokenQ.data.role}</dd>
              <dt className="text-sf-ink-3">iat（Unix 秒）</dt>
              <dd className="text-sf-ink">{tokenQ.data.iat}</dd>
              <dt className="text-sf-ink-3">exp（Unix 秒）</dt>
              <dd className="text-sf-ink">{tokenQ.data.exp}</dd>
            </dl>
          )}
        </QueryState>
      </Card>

      <Card title="登录历史">
        <QueryState
          isLoading={loginsQ.isLoading}
          isError={loginsQ.isError}
          error={loginsQ.error}
          isEmpty={loginsQ.data?.length === 0}
          emptyLabel="暂无登录记录"
        >
          <ul className="space-y-1">
            {loginsQ.data?.map((l) => (
              <li
                key={l.id}
                className="rounded-tile bg-sf-surface-2 px-2 py-1.5 text-body text-sf-ink-2"
              >
                {l.created_at} · {l.action} · {l.detail}
              </li>
            ))}
          </ul>
        </QueryState>
      </Card>

      <Card title="偏好设置">
        <div className="space-y-2">
          <textarea
            aria-label="偏好设置 JSON"
            value={settingsText}
            placeholder='{"theme_mode": "dark"}'
            onChange={(e) => setSettingsText(e.target.value)}
            rows={4}
            className="w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={submitSettings}
              disabled={settingsM.isPending}
              className="rounded-tile bg-sf-accent px-3 py-1.5 text-body text-white disabled:opacity-60"
            >
              {settingsM.isPending ? '保存中…' : '保存设置'}
            </button>
            {settingsM.isSuccess && <span className="text-xs text-sf-ok">设置已保存</span>}
          </div>
          {settingsError && <ErrorState message={settingsError} />}
          {settingsM.isError && <ErrorState message={errMsg(settingsM.error)} />}
        </div>
      </Card>

      <Card title="头像">
        <div className="space-y-2">
          <input
            aria-label="头像文件"
            type="file"
            accept="image/*"
            onChange={onAvatarFile}
            className="text-body text-sf-ink-2"
          />
          <p className="text-xs text-sf-ink-3">仅接受 data:image/ 开头的图片，体积 ≤3MB。</p>
          {avatarM.isSuccess && <span className="text-xs text-sf-ok">头像已保存</span>}
          {avatarError && <ErrorState message={avatarError} />}
          {avatarM.isError && <ErrorState message={errMsg(avatarM.error)} />}
        </div>
      </Card>

      <Card title="退出登录">
        <div className="space-y-2">
          <button
            type="button"
            onClick={submitLogout}
            disabled={logoutM.isPending}
            className="rounded-tile border border-sf-line px-3 py-1.5 text-body text-sf-ink-2 hover:text-sf-danger disabled:opacity-60"
          >
            {logoutM.isPending ? '登出中…' : '退出登录'}
          </button>
          {logoutM.isError && <ErrorState message={errMsg(logoutM.error)} />}
        </div>
      </Card>
    </div>
  )
}
