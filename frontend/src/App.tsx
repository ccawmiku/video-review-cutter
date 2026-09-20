import * as React from "react"
import { AppShell } from "@/components/layout/AppShell"
import { ReviewQueue } from "@/components/videos/ReviewQueue"
import { VideoPreview } from "@/components/videos/VideoPreview"
import { TaskModeBar } from "@/components/videos/TaskModeBar"
import { fetchVideos, recordDecision } from "@/api/videoClient"
import { ReviewDecision, VideoItem, VideoStatus } from "@/types/video"
import { AlertCircle, CheckCircle2 } from "lucide-react"

interface BackendHealth {
  status: string
  app: string
  version: string
  environment: string
  database?: { status: string; type: string }
  ffmpeg?: { available: boolean; status: string }
  storage?: { video_roots_count: number; archive_configured: boolean; discarded_configured: boolean }
}

export function App() {
  const [health, setHealth] = React.useState<BackendHealth | null>(null)

  // 视频列表与分页状态
  const [videos, setVideos] = React.useState<VideoItem[]>([])
  const [selectedVideo, setSelectedVideo] = React.useState<VideoItem | null>(null)
  const [statusFilter, setStatusFilter] = React.useState<VideoStatus | "all">("all")
  const [page, setPage] = React.useState<number>(1)
  const [pageSize, setPageSize] = React.useState<number>(20)
  const [total, setTotal] = React.useState<number>(0)
  const [totalPages, setTotalPages] = React.useState<number>(1)
  const [unprocessedTotal, setUnprocessedTotal] = React.useState<number>(0)

  // 加载与错误状态
  const [isLoading, setIsLoading] = React.useState<boolean>(true)
  const [error, setError] = React.useState<string | null>(null)

  // 任务模式状态
  const [isTaskMode, setIsTaskMode] = React.useState<boolean>(false)
  const [isSubmittingDecision, setIsSubmittingDecision] = React.useState<boolean>(false)
  const [feedbackNotice, setFeedbackNotice] = React.useState<{
    type: "success" | "error"
    message: string
  } | null>(null)

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"

  // 获取后端健康检查
  React.useEffect(() => {
    fetch(`${apiBaseUrl}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`)
        return res.json()
      })
      .then((data: BackendHealth) => {
        setHealth(data)
      })
      .catch(() => {
        // Backend offline or error handled gracefully
      })
  }, [apiBaseUrl])

  // 加载待处理视频总数（用于全局任务模式指示器）
  const loadUnprocessedCount = React.useCallback(async () => {
    try {
      const res = await fetchVideos(apiBaseUrl, {
        status: "unprocessed",
        page: 1,
        pageSize: 1,
      })
      setUnprocessedTotal(res.total)
    } catch {
      // ignore silently for offline mode
    }
  }, [apiBaseUrl])

  // 加载视频列表（默认按时长降序）
  const loadVideos = React.useCallback(
    async (currentPage = page, currentFilter = statusFilter, currentPageSize = pageSize) => {
      setIsLoading(true)
      setError(null)

      try {
        const response = await fetchVideos(apiBaseUrl, {
          page: currentPage,
          pageSize: currentPageSize,
          status: currentFilter,
          sortBy: "duration",
          order: "desc",
        })

        setVideos(response.items)
        setTotal(response.total)
        setTotalPages(response.total_pages || 1)

        // 默认选中项逻辑
        setSelectedVideo((prevSelected) => {
          if (prevSelected) {
            const fresh = response.items.find((v) => v.id === prevSelected.id)
            if (fresh) return fresh
          }
          return response.items[0] ?? null
        })

        void loadUnprocessedCount()
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "获取视频失败"
        setError(message)
      } finally {
        setIsLoading(false)
      }
    },
    [apiBaseUrl, page, statusFilter, pageSize, loadUnprocessedCount]
  )

  // 依赖项变化触发请求
  React.useEffect(() => {
    void loadVideos(page, statusFilter, pageSize)
  }, [loadVideos, page, statusFilter, pageSize])

  // 待处理视频集合（当前列表内）
  const unprocessedVideosInList = React.useMemo(() => {
    return videos.filter((v) => v.status === "unprocessed")
  }, [videos])

  // 当前选中的待处理视频在未处理集合中的序号
  const currentUnprocessedIndex = React.useMemo(() => {
    if (!selectedVideo) return -1
    return unprocessedVideosInList.findIndex((v) => v.id === selectedVideo.id)
  }, [selectedVideo, unprocessedVideosInList])

  // 推进到下一个待处理视频
  const advanceToNextUnprocessed = React.useCallback(
    (currentId?: number) => {
      const remaining = videos.filter((v) => v.status === "unprocessed" && v.id !== currentId)
      if (remaining.length > 0) {
        setSelectedVideo(remaining[0])
      } else {
        // 如果当前页无待处理项，检查是否可刷新或已全部完成
        setSelectedVideo(null)
        setFeedbackNotice({
          type: "success",
          message: "当前列表中已无未处理视频，审核任务已全部推进完成！",
        })
      }
    },
    [videos]
  )

  // 进入任务模式
  const handleStartTaskMode = () => {
    setIsTaskMode(true)
    // 优先选中第一个待处理项
    const firstUnprocessed = videos.find((v) => v.status === "unprocessed")
    if (firstUnprocessed) {
      setSelectedVideo(firstUnprocessed)
    }
    setFeedbackNotice(null)
  }

  // 退出任务模式
  const handleExitTaskMode = () => {
    setIsTaskMode(false)
  }

  // 跳过当前项
  const handleSkipTask = () => {
    if (!selectedVideo) return
    const currentIdx = unprocessedVideosInList.findIndex((v) => v.id === selectedVideo.id)
    if (currentIdx >= 0 && currentIdx < unprocessedVideosInList.length - 1) {
      setSelectedVideo(unprocessedVideosInList[currentIdx + 1])
    } else if (unprocessedVideosInList.length > 0) {
      setSelectedVideo(unprocessedVideosInList[0])
    }
  }

  // 提交审核决策 (no_action 或 clip_selected)
  const handleRecordDecision = async (decision: ReviewDecision) => {
    if (!selectedVideo) return

    setIsSubmittingDecision(true)
    setFeedbackNotice(null)

    try {
      const updated = await recordDecision(apiBaseUrl, selectedVideo.id, decision)

      // 更新列表内该视频状态
      setVideos((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedVideo(updated)

      // 递减待处理总数
      setUnprocessedTotal((prev) => Math.max(0, prev - 1))

      const decisionName = decision === "no_action" ? "无需处理 (No action)" : "片段已选 (Clip selected)"
      setFeedbackNotice({
        type: "success",
        message: `已将「${updated.filename}」成功记录为：${decisionName}`,
      })

      // 任务模式下自动推进到下一个待处理视频
      if (isTaskMode) {
        advanceToNextUnprocessed(updated.id)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "提交决策失败"
      setFeedbackNotice({
        type: "error",
        message: `决策提交失败: ${message}`,
      })
    } finally {
      setIsSubmittingDecision(false)
    }
  }

  // 全局键盘快捷键（仅任务模式有效）
  React.useEffect(() => {
    if (!isTaskMode) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // 避免在输入组件中触发快捷键
      const target = e.target as HTMLElement
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      ) {
        return
      }

      if (e.key === "Escape") {
        handleExitTaskMode()
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isTaskMode])

  // 筛选与分页控制处理函数
  const handleFilterChange = (newStatus: VideoStatus | "all") => {
    setStatusFilter(newStatus)
    setPage(1)
  }

  const handlePageChange = (newPage: number) => {
    setPage(newPage)
  }

  const handlePageSizeChange = (newPageSize: number) => {
    setPageSize(newPageSize)
    setPage(1)
  }

  const handleRefresh = () => {
    void loadVideos(page, statusFilter, pageSize)
  }

  return (
    <AppShell
      backendStatus={health?.status === "ok" ? "connected" : "checking"}
      apiBaseUrl={apiBaseUrl}
    >
      <div className="space-y-6">
        {/* 操作反馈浮条 */}
        {feedbackNotice && (
          <div
            role="status"
            aria-live="polite"
            className={`flex items-center justify-between gap-2 rounded-lg p-3 text-xs border ${
              feedbackNotice.type === "success"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
                : "bg-destructive/10 border-destructive/30 text-destructive dark:text-rose-300"
            }`}
          >
            <div className="flex items-center gap-2">
              {feedbackNotice.type === "success" ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
              )}
              <span>{feedbackNotice.message}</span>
            </div>
            <button
              onClick={() => setFeedbackNotice(null)}
              className="font-medium underline hover:opacity-80"
              aria-label="关闭通知"
            >
              关闭
            </button>
          </div>
        )}

        {/* 核心工作流区域：左侧队列列表，右侧任务模式与视频预览 */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* 左侧：视频审核队列 */}
          <div className="lg:col-span-7 space-y-4">
            <ReviewQueue
              videos={videos}
              selectedVideoId={selectedVideo?.id ?? null}
              currentStatusFilter={statusFilter}
              page={page}
              pageSize={pageSize}
              total={total}
              totalPages={totalPages}
              unprocessedCount={unprocessedTotal}
              isLoading={isLoading}
              error={error}
              isTaskMode={isTaskMode}
              onSelectVideo={(video) => setSelectedVideo(video)}
              onFilterChange={handleFilterChange}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
              onRefresh={handleRefresh}
              onStartTaskMode={handleStartTaskMode}
            />
          </div>

          {/* 右侧：任务模式控制台与视频播放预览 */}
          <div className="lg:col-span-5 space-y-4 sticky top-20">
            {isTaskMode && (
              <TaskModeBar
                currentVideo={
                  selectedVideo?.status === "unprocessed" ? selectedVideo : (unprocessedVideosInList[0] ?? null)
                }
                unprocessedCount={unprocessedVideosInList.length}
                currentIndex={currentUnprocessedIndex}
                totalUnprocessed={unprocessedVideosInList.length}
                isSubmitting={isSubmittingDecision}
                onDecision={handleRecordDecision}
                onSkip={handleSkipTask}
                onExit={handleExitTaskMode}
              />
            )}

            <VideoPreview
              video={selectedVideo}
              apiBaseUrl={apiBaseUrl}
            />
          </div>
        </div>
      </div>
    </AppShell>
  )
}

export default App
