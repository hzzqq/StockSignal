import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Card } from '@/shared/ui/Card'
import { ErrorState, QueryState } from '@/shared/ui/States'
import { Textarea } from '@/shared/ui/Field'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import type { ForumPost } from '@/api/schemas/community'
import {
  useForumPosts,
  useForumPost,
  useCreatePost,
  useDeletePost,
  useLikePost,
  useAddComment,
} from '@/lib/queriesCommunity'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'
import { Button } from '@/shared/ui/Button'
import { useToast } from '@/shared/ui/Toast'


function StockTag({
  code,
  name,
  onOpen,
}: {
  code: string
  name: string
  onOpen: (code: string) => void
}) {
  if (!code) return null
  return (
    <Button type="button" onClick={() => onOpen(code)} variant="secondary" size="sm">
      {name || code}（{code}）→ 个股研究
    </Button>
  )
}

function PostRow({
  p,
  onOpenPost,
  onOpenStock,
}: {
  p: ForumPost
  onOpenPost: (id: number) => void
  onOpenStock: (code: string) => void
}) {
  return (
    <li className="rounded-tile border border-sf-line bg-sf-surface px-4 py-3 transition-colors hover:border-sf-accent">
      <div className="flex gap-3">
        <Avatar name={p.username} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start gap-2">
            <Button
              type="button"
              onClick={() => onOpenPost(p.id)}
              variant="ghost"
              size="sm"
              className="h-auto justify-start whitespace-normal text-left font-semibold text-sf-ink"
            >
              {p.title}
            </Button>
            <StockTag code={p.stock_code} name={p.stock_name} onOpen={onOpenStock} />
          </div>
          {p.excerpt && <p className="mt-1 line-clamp-2 text-label text-sf-ink-3">{p.excerpt}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-label text-sf-ink-3">
            <span>{p.username}</span>
            <span>{displayTime(p.created_at)}</span>
            <span>回复 {displayCount(p.comment_count)}</span>
            <span>赞 {p.likes}</span>
            <span>浏览 {p.views}</span>
          </div>
        </div>
      </div>
    </li>
  )
}

/**
 * 股吧社区（/forum）：列表 / 详情两态，真实接后端 forum 写端点。

/**
 * 股吧社区（/forum）：列表 / 详情两态，真实接后端 forum 写端点。
 *
 * 版式对标主流股吧：左侧主题流（标题 + 股票标签 + 摘要 + 回复/浏览/赞），
 * 右侧发帖区与社区须知；详情页主贴 + 评论区，关联股票可深链到个股研究。
 *
 * 诚实红线：
 *  - 加载 / 错误 / 空 / 有数据由 QueryState 如实分发，取数失败显示真实错误文案；
 *  - 写失败显示后端 ApiError 的真实 message，绝不洗成成功；
 *  - comment_count / created_at 缺失显「—」，不用 ?? 0 / || 0 冒充真实值；
 *  - 不用 new Date() 冒充数据日；关联股票未知名称不臆造。
 */
function displayCount(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : String(v)
}

function displayTime(v: string | null | undefined): string {
  return v ? v.slice(0, 10) : '—'
}

function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-sf-line bg-sf-surface-2 text-label text-sf-accent"
    >
      {name ? name.slice(0, 1).toUpperCase() : '股'}
    </span>
  )
}

export function ForumView() {
  const navigate = useNavigate()
  const { push } = useToast()

  const [stockCode, setStockCode] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [postStockCode, setPostStockCode] = useState('')
  const [postStockName, setPostStockName] = useState('')
  const [commentText, setCommentText] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const listQ = useForumPosts(stockCode)
  const detailQ = useForumPost(selectedId)
  const createM = useCreatePost()
  const deleteM = useDeletePost()
  const likeM = useLikePost()
  const commentM = useAddComment()

  const errMsg = (e: unknown): string => (e instanceof Error ? e.message : '操作失败')
  const detailError = [likeM.error, commentM.error, deleteM.error].find(
    (e): e is Error => e instanceof Error,
  )

  function openPost(id: number) {
    setSelectedId(id)
    setConfirmingDelete(false)
    setCommentText('')
  }

  function backToList() {
    setSelectedId(null)
    setConfirmingDelete(false)
  }

  function goStock(code: string) {
    void navigate({ to: '/stock/research', search: { code } })
  }

  function submitCreate() {
    createM.mutate(
      { title, content, stock_code: postStockCode, stock_name: postStockName },
      {
        onSuccess: () => {
          setTitle('')
          setContent('')
          setPostStockCode('')
          setPostStockName('')
          push('发布成功', 'ok')
        },
      },
    )
  }

  function submitLike() {
    if (selectedId !== null) likeM.mutate(selectedId)
  }

  function submitComment() {
    if (selectedId === null) return
    commentM.mutate(
      { postId: selectedId, content: commentText },
      {
        onSuccess: () => {
          setCommentText('')
          push('评论成功', 'ok')
        },
      },
    )
  }

  function submitDelete() {
    if (selectedId === null) return
    deleteM.mutate(selectedId, {
      onSuccess: () => {
        setConfirmingDelete(false)
        backToList()
      },
    })
  }


  return (
    <div className="flow">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <SectionTitle as="h2">股吧社区</SectionTitle>
        <span className="text-label text-sf-ink-3">
          发帖 / 评论 / 点赞 / 删除 · 社区数据（演示态为 MSW 模拟响应，非真实后端数据）。
        </span>
      </div>

      {selectedId === null ? (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="flow">
            <Card title="按股票筛选">
              <div className="flex flex-wrap items-end gap-3">
                <div className="w-72">
                  <StockSearchInput
                    label="按股票筛选（代码 / 名称 / 首字母）"
                    value={stockCode}
                    placeholder="留空显示全部帖子"
                    onSelect={(code) => setStockCode(code)}
                  />
                </div>
                {stockCode && (
                  <Button
                    type="button"
                    onClick={() => setStockCode('')}
                    variant="ghost"
                    size="sm"
                  >
                    清除筛选
                  </Button>
                )}
                <span className="pb-1 text-label text-sf-ink-3">
                  当前筛选：{stockCode === '' ? '全部' : stockCode}
                </span>
              </div>
            </Card>

            <Card title="帖子列表">
              <QueryState
                isLoading={listQ.isLoading}
                isError={listQ.isError}
                error={listQ.error}
                isEmpty={listQ.data?.length === 0}
                emptyLabel="暂无帖子"
              >
                <ul className="space-y-2">
                  {listQ.data?.map((p) => (
                    <PostRow key={p.id} p={p} onOpenPost={openPost} onOpenStock={goStock} />
                  ))}
                </ul>
              </QueryState>
            </Card>
          </div>

          <div className="flow">
            <Card title="发表新帖">
              <div className="space-y-3">
                <div>
                  <label htmlFor="forum-title" className="mb-1 block text-label text-sf-ink-3">
                    标题
                  </label>
                  <input
                    id="forum-title"
                    aria-label="帖子标题"
                    type="text"
                    value={title}
                    placeholder="标题（必填，≤200 字）"
                    onChange={(e) => setTitle(e.target.value)}
                    className="w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
                  />
                </div>
                <div>
                  <label htmlFor="forum-content" className="mb-1 block text-label text-sf-ink-3">
                    正文
                  </label>
                  <Textarea
                    id="forum-content"
                    aria-label="帖子内容"
                    value={content}
                    placeholder="分享你的研究逻辑与依据（必填，≤20000 字）"
                    onChange={(e) => setContent(e.target.value)}
                    rows={5}
                  />
                </div>
                <StockSearchInput
                  label="关联股票（可选）"
                  value={postStockCode}
                  onSelect={(code, item) => {
                    setPostStockCode(code)
                    setPostStockName(item?.name ?? '')
                  }}
                />
                {postStockCode && (
                  <p className="text-label text-sf-ink-3">
                    已关联：{postStockName || postStockCode}（{postStockCode}）
                  </p>
                )}
                <Button
                  type="button"
                  onClick={submitCreate}
                  disabled={createM.isPending}
                  variant="primary"
                  className="w-full"
                >
                  {createM.isPending ? '发布中…' : '发布帖子'}
                </Button>
                {createM.isError && <ErrorState message={errMsg(createM.error)} />}
              </div>
            </Card>

            <Card title="社区须知">
              <ul className="space-y-2 text-label text-sf-ink-2">
                <li>· 讨论请围绕个股基本面、公告与可验证数据，拒绝纯情绪刷屏。</li>
                <li>· 观点请标注依据与数据日，未证实消息不要当作事实发布。</li>
                <li>· 尊重不同判断，不攻击其他用户；违规内容可被删除。</li>
                <li>
                  {`· `}
                  <LeadText>社区文本仅代表发帖人观点，不构成投资建议</LeadText>
                  {`。`}
                </li>
              </ul>
            </Card>
          </div>
        </div>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="flow">
            <Button
              type="button"
              onClick={backToList}
              variant="ghost"
              size="sm"
              className="w-fit"
            >
              ← 返回帖子列表
            </Button>

            <QueryState
              isLoading={detailQ.isLoading}
              isError={detailQ.isError}
              error={detailQ.error}
              emptyLabel="帖子不存在"
            >
              {detailQ.data && (
                <Card title={detailQ.data.title}>
                  <div className="space-y-4">
                    <div className="flex items-center gap-3 border-b border-sf-line pb-3">
                      <Avatar name={detailQ.data.username} />
                      <div className="text-label text-sf-ink-3">
                        <div className="text-body text-sf-ink">{detailQ.data.username}</div>
                        <div>
                          {displayTime(detailQ.data.created_at)} · 浏览 {detailQ.data.views}
                        </div>
                      </div>
                    </div>

                    <StockTag
                      code={detailQ.data.stock_code}
                      name={detailQ.data.stock_name}
                      onOpen={goStock}
                    />

                    <p className="whitespace-pre-wrap text-body leading-relaxed text-sf-ink">
                      {detailQ.data.content}
                    </p>

                    <div className="flex flex-wrap items-center gap-2 border-t border-sf-line pt-3">
                      <Button
                        type="button"
                        onClick={submitLike}
                        disabled={likeM.isPending}
                        variant="secondary"
                        size="sm"
                      >
                        {likeM.isPending ? '点赞中…' : `点赞（${detailQ.data.likes}）`}
                      </Button>
                      {!confirmingDelete && (
                        <Button
                          type="button"
                          onClick={() => setConfirmingDelete(true)}
                          variant="danger"
                          size="sm"
                        >
                          删除帖子
                        </Button>
                      )}
                      {confirmingDelete && (
                        <>
                          <span className="text-label text-sf-ink-2">确认删除该帖子？</span>
                          <Button
                            type="button"
                            onClick={submitDelete}
                            disabled={deleteM.isPending}
                            variant="danger"
                            size="sm"
                          >
                            确认删除
                          </Button>
                          <Button
                            type="button"
                            onClick={() => setConfirmingDelete(false)}
                            variant="ghost"
                            size="sm"
                          >
                            取消
                          </Button>
                        </>
                      )}
                    </div>
                    {detailError && <ErrorState message={detailError.message} />}

                    <div className="border-t border-sf-line pt-3">
                      <h4 className="text-body font-medium text-sf-ink-2">
                        评论（{detailQ.data.comments.length}）
                      </h4>
                      {detailQ.data.comments.length === 0 && (
                        <p className="text-label text-sf-ink-3">暂无评论</p>
                      )}
                      <ul className="mt-2 space-y-2">
                        {detailQ.data.comments.map((c) => (
                          <li
                            key={c.id}
                            className="flex gap-2 rounded-tile bg-sf-surface-2 px-3 py-2 text-body text-sf-ink-2"
                          >
                            <Avatar name={c.username} />
                            <div className="min-w-0">
                              <div className="text-label text-sf-ink-3">
                                {c.username} · {displayTime(c.created_at)}
                              </div>
                              <div className="text-body">{c.content}</div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="space-y-2 border-t border-sf-line pt-3">
                      <label htmlFor="forum-comment" className="block text-label text-sf-ink-3">
                        参与讨论
                      </label>
                      <Textarea
                        id="forum-comment"
                        aria-label="评论内容"
                        value={commentText}
                        placeholder="发表评论…"
                        onChange={(e) => setCommentText(e.target.value)}
                        rows={3}
                      />
                      <Button
                        type="button"
                        onClick={submitComment}
                        disabled={commentM.isPending}
                        variant="primary"
                        size="sm"
                      >
                        {commentM.isPending ? '发表中…' : '发表评论'}
                      </Button>
                    </div>
                  </div>
                </Card>
              )}
            </QueryState>
          </div>

          <Card title="讨论提示">
            <ul className="space-y-2 text-label text-sf-ink-2">
              <li>· 点赞代表认同，不代表数据结论。</li>
              <li>· 点击关联股票可跳转到个股研究查看原始数据。</li>
              <li>· 评论与发帖失败会显示后端真实原因，不会伪装成功。</li>
            </ul>
          </Card>
        </div>
      )}
    </div>
  )
}
