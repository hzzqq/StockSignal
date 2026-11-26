import { useEffect, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react'
import { useReviewNotes } from '@/lib/queries'
import { useSaveReviewNotes, useUploadReviewImage } from '@/lib/queriesBatchB'
import { reviewImagePrecheckError } from '@/api/batchB'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { Input, Textarea } from '@/shared/ui/Field'
import { Skeleton } from '@/shared/ui/Skeleton'
import { EmptyStateModern } from '@/shared/ui/EmptyStateModern'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'
import { useToast } from '@/shared/ui/Toast'

/** 本次会话内刚上传图片的 objectURL 预览项。 */
interface UploadedPreview {
  filename: string
  objectUrl: string
}

/**
 * 99 决策问答（v2 native /review-notes）：逐日复盘笔记（51 页复盘段的原文 md）。
 * 复用 /review-notes?date=。诚实红线：本地若无该日期复盘笔记（review_notes_<date>.md 缺失），
 * 后端返回 not_found → 页面显「该日期暂无复盘笔记」，不编造内容；内容按纯文本呈现（不引入 markdown 依赖）。
 * 注：本环境尚未生成任何 review_notes 文件，故默认即诚实空态；若日后生成则自动显示。
 *
 * 图片上传（51 晨报 parity）：
 * - 选择文件（点击上传区或拖拽到上传区）→ 前置校验（扩展名白名单 png/jpg/jpeg/gif/webp + ≤5MB，
 *   不合规不发请求）→ POST multipart 上传 → 成功后把 `![文件名](url)` 追加进 draft（前加空行），
 *   随保存表单一起 PUT。
 * - 历史图片预览限制（有意设计）：GET /api/v2/read/review-images/<date>/<filename> 受 JWT 保护，
 *   <img> 无法携带 Authorization 头，故不用 <img src> 直连服务端 URL。刚上传的图用
 *   URL.createObjectURL 在本次会话内预览；历史图片降级为「链接已写入笔记文本」，不渲染 img。
 */
export function ReviewNotes() {
  const [date, setDate] = useState<string>('2026-09-21')
  const q = useReviewNotes(date)
  const saveM = useSaveReviewNotes()
  const uploadM = useUploadReviewImage()
  const [draft, setDraft] = useState('')
  const [previews, setPreviews] = useState<UploadedPreview[]>([])
  // 拖拽悬停态：给上传区一个可感知的高亮反馈
  const [dragActive, setDragActive] = useState(false)
  // ref 记录全部已发 objectURL，供切换日期 / 卸载时统一 revoke，避免内存泄漏
  const objectUrlsRef = useRef<string[]>([])
  // 隐藏 file input：上传区可视化外壳点击 / 拖拽时触发同一 input 与校验逻辑
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { push } = useToast()

  function clearPreviews() {
    for (const u of objectUrlsRef.current) URL.revokeObjectURL(u)
    objectUrlsRef.current = []
    setPreviews([])
  }

  // 切换日期只复位编辑区与保存态：不自动把原文回填进 textarea，
  // 否则同一段正文会在只读区与编辑框重复出现；需要修改时主动点「载入原文」。
  useEffect(() => {
    setDraft('')
    saveM.reset()
    uploadM.reset()
    clearPreviews()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date])

  // 卸载时释放 objectURL
  useEffect(
    () => () => {
      for (const u of objectUrlsRef.current) URL.revokeObjectURL(u)
    },
    [],
  )

  function handleSave(e: FormEvent) {
    e.preventDefault()
    saveM.reset()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      push('日期须为真实 YYYY-MM-DD', 'warn')
      return
    }
    saveM.mutate(
      { date, content: draft },
      {
        onSuccess: () => push(`已保存 ${date} 的复盘笔记（服务端原文）`, 'ok'),
        onError: (err) =>
          push(`保存失败：${err instanceof Error ? err.message : String(err)}`, 'danger'),
      },
    )
  }

  function uploadImage(file: File) {
    // 前置校验（与后端双重校验同口径）：不合规直接提示，不发请求
    const preErr = reviewImagePrecheckError(file)
    if (preErr) {
      uploadM.reset()
      push(`图片不合规：${preErr}`, 'danger')
      return
    }
    uploadM.mutate(
      { file, date },
      {
        onSuccess: (data) => {
          // v1 语义：Markdown 图片链接前加空行追加进笔记文本，随保存表单一起提交
          setDraft((prev) => (prev ? `${prev}\n\n` : '') + `![${data.filename}](${data.url})`)
          const objectUrl = URL.createObjectURL(file)
          objectUrlsRef.current.push(objectUrl)
          setPreviews((p) => [...p, { filename: data.filename, objectUrl }])
          push(`图片上传成功：${data.filename}`, 'ok')
        },
        onError: (err) =>
          push(`上传失败：${err instanceof Error ? err.message : String(err)}`, 'danger'),
      },
    )
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // 允许重复选择同一文件再次上传
    if (!file) return
    uploadImage(file)
  }

  function handleDragOver(e: DragEvent<HTMLButtonElement>) {
    e.preventDefault() // 允许 drop
    setDragActive(true)
  }

  function handleDrop(e: DragEvent<HTMLButtonElement>) {
    e.preventDefault()
    setDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (file) uploadImage(file)
  }

  return (
    <div className="space-y-4">
      <SectionTitle as="h2">决策问答</SectionTitle>
      <p className="text-xs text-sf-ink-3">
        {`逐日复盘笔记（只读视图）。本地若无该日期复盘笔记，会如实显示「暂无」，`}
        <LeadText>不编造</LeadText>
        {`。`}
      </p>

      <Card className="transition-shadow hover:shadow-e2">
        <div className="flex flex-wrap items-end gap-4">
          <Input
            type="date"
            label="选择日期"
            value={date}
            onChange={(e) => setDate(e.target.value || '')}
            className="w-56"
          />
          {q.isLoading && (
            <div className="min-w-40 flex-1 pb-2">
              <Skeleton rows={2} />
            </div>
          )}
        </div>
      </Card>

      {q.data && (
        <Card
          title={`复盘笔记 · ${q.data.date}`}
          className="transition-shadow hover:shadow-e2"
        >
          <pre className="whitespace-pre-wrap text-sm text-sf-ink-2">{q.data.content}</pre>
        </Card>
      )}
      {q.isError && (
        <EmptyStateModern
          title="该日期暂无复盘笔记"
          description={q.error instanceof Error ? q.error.message : undefined}
        />
      )}

      <Card title="编辑并保存复盘笔记" className="transition-shadow hover:shadow-e2">
        <form onSubmit={handleSave} className="space-y-3">
          <Textarea
            aria-label="复盘笔记正文"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={10}
            placeholder="填写该日期的 Markdown 复盘笔记；保存后覆盖服务端同名文件。"
            className="[&_textarea]:whitespace-pre-wrap [&_textarea]:font-mono"
          />
          <div className="space-y-2">
            <p className="text-xs text-sf-ink-2">
              插入图片（png/jpg/jpeg/gif/webp，≤5MB；成功后以 Markdown 链接追加进正文）
            </p>
            <input
              ref={fileInputRef}
              type="file"
              aria-label="选择复盘图片"
              accept="image/png,image/jpeg,image/gif,image/webp"
              disabled={uploadM.isPending}
              onChange={handleFileChange}
              className="sr-only"
            />
            <button
              type="button"
              disabled={uploadM.isPending}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={handleDragOver}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              className={`flex w-full cursor-pointer flex-col items-center gap-1 rounded-tile border border-dashed p-4 text-center transition-colors disabled:pointer-events-none disabled:opacity-50 ${
                dragActive
                  ? 'border-sf-accent bg-sf-surface-2'
                  : 'border-sf-line hover:border-sf-accent'
              }`}
            >
              <span aria-hidden="true" className="text-sf-ink-3">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-6 w-6"
                >
                  <path d="M12 16V4m0 0 4 4m-4-4-4 4" />
                  <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
                </svg>
              </span>
              <span className="text-xs text-sf-ink-2">
                点击或拖拽图片到此处（png/jpg/jpeg/gif/webp，≤5MB）
              </span>
            </button>
            {uploadM.isPending && <Skeleton className="max-w-56" />}
          </div>
          {previews.length > 0 && (
            <div className="space-y-2">
              {previews.map((p) => (
                <div key={p.objectUrl}>
                  {/* 本次会话内 objectURL 预览（见组件注释：服务端图片 URL 受 JWT 保护，
                      <img> 无法带 Authorization 头，故不用服务端 URL 直连渲染） */}
                  <img
                    src={p.objectUrl}
                    alt={p.filename}
                    className="max-h-40 rounded border border-sf-line"
                  />
                  <p className="text-xs text-sf-ink-3">刚上传：{p.filename}（本次会话内预览）</p>
                </div>
              ))}
              <p className="text-xs text-sf-ink-3">
                历史图片预览需登录态，暂以内嵌链接呈现：图片链接已写入笔记文本，不做服务端直连渲染。
              </p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            {q.data?.content && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDraft(q.data?.content ?? '')}
              >
                载入原文到编辑区
              </Button>
            )}
            <Button type="submit" variant="primary" size="sm" disabled={saveM.isPending}>
              {saveM.isPending ? '保存中…' : `保存 ${date} 的笔记`}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
