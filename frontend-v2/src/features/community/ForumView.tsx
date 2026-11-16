import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Card } from '@/shared/ui/Card'
import { ErrorState, QueryState } from '@/shared/ui/States'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import {
  useForumPosts,
  useForumPost,
  useCreatePost,
  useDeletePost,
  useLikePost,
  useAddComment,
} from '@/lib/queriesCommunity'

/**
 * 股吧社区（/forum）：列表 / 详情两态，真实接后端 forum 写端点。
 *
 * 能力：按股票代码筛选、发帖（标题/内容/关联股票 StockSearchInput）、打开详情看评论、
 * 发表评论、点赞、删除帖子（带二次确认）、点击关联股票深链到 /stock/research?code=。
 *
 * 诚实红线（四态齐全）：
 *  - 加载 / 错误 / 空 / 有数据 由 QueryState 如实分发，取数失败显示真实错误文案；
 *  - 写失败显示后端 ApiError 的真实 message（空标题被拒、非作者删除 400 等），绝不洗成成功；
 *  - 不补零：comment_count / 关联股票名缺失显「—」或省略，不用 `?? 0` / `|| 0`；
 *  - 不用 new Date() 冒充数据日；关联股票未知名称不臆造。
 */
export function ForumView() {
  const navigate = useNavigate()

  // 列表筛选 / 详情态
  const [stockCode, setStockCode] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // 发帖表单
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [postStockCode, setPostStockCode] = useState('')
  const [postStockName, setPostStockName] = useState('')
  // 评论 / 删除二次确认
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
      { onSuccess: () => setCommentText('') },
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
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">股吧社区</h2>
      <p className="text-xs text-sf-ink-3">
        发帖 / 评论 / 点赞 / 删除 · 社区数据（演示态为 MSW 模拟响应，非真实后端数据）。
      </p>

      {selectedId === null ? (
        <>
          <Card title="按股票代码筛选">
            <div className="flex items-center gap-2">
              <input
                aria-label="股票代码筛选"
                type="text"
                value={stockCode}
                placeholder="如 600519，留空显示全部"
                onChange={(e) => setStockCode(e.target.value)}
                className="w-64 rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
              />
              {stockCode && (
                <button
                  type="button"
                  onClick={() => setStockCode('')}
                  className="rounded-tile border border-sf-line px-2 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent"
                >
                  清除筛选
                </button>
              )}
              <span className="text-xs text-sf-ink-3">
                当前筛选：{stockCode === '' ? '全部' : stockCode}
              </span>
            </div>
          </Card>

          <Card title="发表新帖">
            <div className="space-y-2">
              <input
                aria-label="帖子标题"
                type="text"
                value={title}
                placeholder="标题（必填，≤200 字）"
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
              />
              <textarea
                aria-label="帖子内容"
                value={content}
                placeholder="内容（必填，≤20000 字）"
                onChange={(e) => setContent(e.target.value)}
                rows={3}
                className="w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
              />
              <StockSearchInput
                label="关联股票（可选）"
                value={postStockCode}
                onSelect={(code, item) => {
                  setPostStockCode(code)
                  setPostStockName(item?.name ?? '')
                }}
              />
              {postStockCode && (
                <p className="text-xs text-sf-ink-3">
                  已关联：{postStockName || postStockCode}（{postStockCode}）
                </p>
              )}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={submitCreate}
                  disabled={createM.isPending}
                  className="rounded-tile bg-sf-accent px-3 py-1.5 text-body text-white disabled:opacity-60"
                >
                  {createM.isPending ? '发布中…' : '发布帖子'}
                </button>
                {createM.isSuccess && <span className="text-xs text-sf-ok">发布成功</span>}
              </div>
              {createM.isError && <ErrorState message={errMsg(createM.error)} />}
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
                  <li key={p.id} className="rounded-tile border border-sf-line p-3">
                    <button
                      type="button"
                      onClick={() => openPost(p.id)}
                      className="text-left text-body font-medium text-sf-ink hover:text-sf-accent"
                    >
                      {p.title}
                    </button>
                    <div className="mt-1 text-xs text-sf-ink-3">
                      {p.username} · 赞 {p.likes} · 浏览 {p.views} · 评论{' '}
                      {p.comment_count === null || p.comment_count === undefined
                        ? '—'
                        : p.comment_count}
                    </div>
                    {p.stock_code && (
                      <button
                        type="button"
                        onClick={() => goStock(p.stock_code)}
                        className="mt-1 text-xs text-sf-accent hover:underline"
                      >
                        {p.stock_name || p.stock_code}（{p.stock_code}）→ 个股研究
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </QueryState>
          </Card>
        </>
      ) : (
        <>
          <button
            type="button"
            onClick={backToList}
            className="rounded-tile border border-sf-line px-2 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent"
          >
            ← 返回列表
          </button>

          <QueryState
            isLoading={detailQ.isLoading}
            isError={detailQ.isError}
            error={detailQ.error}
            emptyLabel="帖子不存在"
          >
            {detailQ.data && (
              <Card title={detailQ.data.title}>
                <div className="space-y-3">
                  <p className="text-xs text-sf-ink-3">
                    {detailQ.data.username} · 赞 {detailQ.data.likes} · 浏览 {detailQ.data.views}
                  </p>
                  {detailQ.data.stock_code && (
                    <button
                      type="button"
                      onClick={() => goStock(detailQ.data.stock_code)}
                      className="text-xs text-sf-accent hover:underline"
                    >
                      关联股票：{detailQ.data.stock_name || detailQ.data.stock_code}（
                      {detailQ.data.stock_code}）→ 个股研究
                    </button>
                  )}
                  <p className="whitespace-pre-wrap text-body text-sf-ink">
                    {detailQ.data.content}
                  </p>

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={submitLike}
                      disabled={likeM.isPending}
                      className="rounded-tile border border-sf-line px-2 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-60"
                    >
                      {likeM.isPending ? '点赞中…' : `点赞（${detailQ.data.likes}）`}
                    </button>
                    {!confirmingDelete && (
                      <button
                        type="button"
                        onClick={() => setConfirmingDelete(true)}
                        className="rounded-tile border border-sf-line px-2 py-1.5 text-label text-sf-ink-2 hover:text-sf-danger"
                      >
                        删除帖子
                      </button>
                    )}
                    {confirmingDelete && (
                      <>
                        <span className="text-xs text-sf-ink-2">确认删除该帖子？</span>
                        <button
                          type="button"
                          onClick={submitDelete}
                          disabled={deleteM.isPending}
                          className="rounded-tile border border-sf-line px-2 py-1.5 text-label text-sf-danger disabled:opacity-60"
                        >
                          确认删除
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmingDelete(false)}
                          className="rounded-tile border border-sf-line px-2 py-1.5 text-label text-sf-ink-2"
                        >
                          取消
                        </button>
                      </>
                    )}
                  </div>
                  {detailError && <ErrorState message={detailError.message} />}

                  <div>
                    <h4 className="text-body font-medium text-sf-ink-2">
                      评论（{detailQ.data.comments.length}）
                    </h4>
                    {detailQ.data.comments.length === 0 && (
                      <p className="text-xs text-sf-ink-3">暂无评论</p>
                    )}
                    <ul className="mt-1 space-y-1">
                      {detailQ.data.comments.map((c) => (
                        <li
                          key={c.id}
                          className="rounded-tile bg-sf-surface-2 px-2 py-1.5 text-body text-sf-ink-2"
                        >
                          <span className="text-sf-ink">{c.username}</span>：{c.content}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="space-y-2">
                    <textarea
                      aria-label="评论内容"
                      value={commentText}
                      placeholder="发表评论…"
                      onChange={(e) => setCommentText(e.target.value)}
                      rows={2}
                      className="w-full rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent"
                    />
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={submitComment}
                        disabled={commentM.isPending}
                        className="rounded-tile bg-sf-accent px-3 py-1.5 text-body text-white disabled:opacity-60"
                      >
                        {commentM.isPending ? '发表中…' : '发表评论'}
                      </button>
                      {commentM.isSuccess && <span className="text-xs text-sf-ok">评论成功</span>}
                    </div>
                  </div>
                </div>
              </Card>
            )}
          </QueryState>
        </>
      )}
    </div>
  )
}
