import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { useReviewNotes } from '@/lib/queries'
import { useSaveReviewNotes, useUploadReviewImage } from '@/lib/queriesBatchB'
import { reviewImagePrecheckError } from '@/api/batchB'
import { Card } from '@/shared/ui/Card'
import { EmptyState } from '@/shared/ui/States'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'

const INPUT_CLS =
  'mt-1 w-full bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

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
 * - 选择文件 → 前置校验（扩展名白名单 png/jpg/jpeg/gif/webp + ≤5MB，不合规不发请求）→
 *   POST multipart 上传 → 成功后把 `![文件名](url)` 追加进 draft（前加空行），随保存表单一起 PUT。
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
  const [notice, setNotice] = useState<string | null>(null)
  const [previews, setPreviews] = useState<UploadedPreview[]>([])
  const [precheckError, setPrecheckError] = useState<string | null>(null)
  // ref 记录全部已发 objectURL，供切换日期 / 卸载时统一 revoke，避免内存泄漏
  const objectUrlsRef = useRef<string[]>([])

  function clearPreviews() {
    for (const u of objectUrlsRef.current) URL.revokeObjectURL(u)
    objectUrlsRef.current = []
    setPreviews([])
  }

  // 切换日期只复位编辑区与保存态：不自动把原文回填进 textarea，
  // 否则同一段正文会在只读区与编辑框重复出现；需要修改时主动点「载入原文」。
  useEffect(() => {
    setDraft('')
    setNotice(null)
    setPrecheckError(null)
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
    setNotice(null)
    saveM.reset()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setNotice('日期须为真实 YYYY-MM-DD')
      return
    }
    saveM.mutate(
      { date, content: draft },
      { onSuccess: () => setNotice(`已保存 ${date} 的复盘笔记（服务端原文）`) },
    )
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // 允许重复选择同一文件再次上传
    if (!file) return
    // 前置校验（与后端双重校验同口径）：不合规直接提示，不发请求
    const preErr = reviewImagePrecheckError(file)
    if (preErr) {
      uploadM.reset()
      setPrecheckError(preErr)
      return
    }
    setPrecheckError(null)
    uploadM.mutate(
      { file, date },
      {
        onSuccess: (data) => {
          // v1 语义：Markdown 图片链接前加空行追加进笔记文本，随保存表单一起提交
          setDraft((prev) => (prev ? `${prev}\n\n` : '') + `![${data.filename}](${data.url})`)
          const objectUrl = URL.createObjectURL(file)
          objectUrlsRef.current.push(objectUrl)
          setPreviews((p) => [...p, { filename: data.filename, objectUrl }])
        },
      },
    )
  }

  const saveError = saveM.error instanceof Error ? saveM.error.message : null
  const uploadError =
    precheckError ??
    (uploadM.error instanceof Error ? uploadM.error.message : null)

  return (
    <div className="space-y-4">
      <SectionTitle as="h2">决策问答</SectionTitle>
      <p className="text-xs text-sf-ink-3">
        {`逐日复盘笔记（只读视图）。本地若无该日期复盘笔记，会如实显示「暂无」，`}
        <LeadText>不编造</LeadText>
        {`。`}
      </p>

      <Card>
        <label className="text-xs text-sf-ink-2">
          选择日期
          <input
            type="date"
            className={INPUT_CLS}
            value={date}
            onChange={(e) => setDate(e.target.value || '')}
          />
        </label>
        {q.isLoading && <span className="ml-2 text-xs text-sf-ink-3">加载中…</span>}
      </Card>

      {q.data && (
        <Card title={`复盘笔记 · ${q.data.date}`}>
          <pre className="whitespace-pre-wrap text-sm text-sf-ink-2">{q.data.content}</pre>
        </Card>
      )}
      {q.isError && (
        <EmptyState
          label="该日期暂无复盘笔记"
          hint={q.error instanceof Error ? q.error.message : undefined}
        />
      )}

      <Card title="编辑并保存复盘笔记">
        <form onSubmit={handleSave} className="space-y-2">
          <textarea
            aria-label="复盘笔记正文"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={10}
            placeholder="填写该日期的 Markdown 复盘笔记；保存后覆盖服务端同名文件。"
            className={`${INPUT_CLS} whitespace-pre-wrap font-mono`}
          />
          <div>
            <label className="text-xs text-sf-ink-2">
              插入图片（png/jpg/jpeg/gif/webp，≤5MB；成功后以 Markdown 链接追加进正文）
              <input
                type="file"
                aria-label="选择复盘图片"
                accept="image/png,image/jpeg,image/gif,image/webp"
                disabled={uploadM.isPending}
                onChange={handleFileChange}
                className={INPUT_CLS}
              />
            </label>
            {uploadM.isPending && <span className="ml-2 text-xs text-sf-ink-2">上传中…</span>}
            {uploadError && (
              <span className="ml-2 text-xs text-sf-danger">
                {precheckError ? '图片不合规：' : '上传失败：'}
                {uploadError}
              </span>
            )}
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
              <button
                type="button"
                onClick={() => setDraft(q.data?.content ?? '')}
                className="text-label px-3 py-1.5 rounded-tile border border-sf-line"
              >
                载入原文到编辑区
              </button>
            )}
            <button
              type="submit"
              disabled={saveM.isPending}
              className="text-label px-3 py-1.5 rounded-tile border border-sf-line disabled:opacity-50"
            >
              {saveM.isPending ? '保存中…' : `保存 ${date} 的笔记`}
            </button>
            {saveError && <span className="text-label text-sf-danger">保存失败：{saveError}</span>}
            {notice && !saveError && <span className="text-label text-sf-ink-2">{notice}</span>}
          </div>
        </form>
      </Card>
    </div>
  )
}
