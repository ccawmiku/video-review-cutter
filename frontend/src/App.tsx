import * as React from "react"
import { AppShell } from "@/components/layout/AppShell"
import { ReviewQueue } from "@/components/videos/ReviewQueue"
import { VideoPreview } from "@/components/videos/VideoPreview"
import { TaskModeBar } from "@/components/videos/TaskModeBar"
import { ClipTimelineEditor } from "@/components/videos/ClipTimelineEditor"
import {
  createVideoClip,
  deleteVideoClip,
  fetchVideoClips,
  fetchVideos,
  recordDecision,
  updateVideoClip,
} from "@/api/videoClient"
import {
  ClipSegment,
  ClipSegmentCreatePayload,
  ClipSegmentUpdatePayload,
  ReviewDecision,
  VideoItem,
  VideoStatus,
} from "@/types/video"
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

  // 片段状态与播放同步
  const [clips, setClips] = React.useState<ClipSegment[]>([])
  const [isLoadingClips, setIsLoadingClips] = React.useState<boolean>(false)
  const [seekTime, setSeekTime] = React.useState<number | null>(null)
  const [currentPlaybackTime, setCurrentPlaybackTime] = React.useState<number | undefined>(undefined)

  // 加载与错误状态
  const [isLoading, setIsLoading] = React.useState<boolean>(true)
  const [isRefreshing, setIsRefreshing] = React.useState<boolean>(false)
  const [error, setError] = React.useState<string | null>(null)
  const hasLoadedRef = React.useRef<boolean>(false)

  // 任务模式状态
  const [isTaskMode, setIsTaskMode] = React.useState<boolean>(false)
  const [isSubmittingDecision, setIsSubmittingDecision] = React.useState<boolean>(false)
  const [feedbackNotice, setFeedbackNotice] = React.useState<{
    type: "success" | "error"
    message: string
  } | null>(null)

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || ""

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
    async (
      currentPage = page,
      currentFilter = statusFilter,
      currentPageSize = pageSize,
      isBackground = false
    ) => {
      if (isBackground || hasLoadedRef.current) {
        setIsRefreshing(true)
      } else {
        setIsLoading(true)
      }
      setError(null)

      try {
        const response = await fetchVideos(apiBaseUrl, {
          page: currentPage,
          pageSize: currentPageSize,
          status: currentFilter,
          sortBy: "duration",
          order: "desc",
        })

        hasLoadedRef.current = true
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
        setIsRefreshing(false)
      }
    },
    [apiBaseUrl, page, statusFilter, pageSize, loadUnprocessedCount]
  )

  // 依赖项变化触发请求
  React.useEffect(() => {
    void loadVideos(page, statusFilter, pageSize)
  }, [loadVideos, page, statusFilter, pageSize])

  // 当选中视频变化时，从后端加载该视频的片段列表
  React.useEffect(() => {
    const currentVideoId = selectedVideo?.id
    if (!currentVideoId) {
      setClips([])
      setIsLoadingClips(false)
      return
    }

    let isCancelled = false
    setIsLoadingClips(true)

    fetchVideoClips(apiBaseUrl, currentVideoId)
      .then((data) => {
        if (!isCancelled) {
          const validClips = Array.isArray(data) ? data : []
          setClips(validClips)
          // 同步到 selectedVideo.clips 及列表以便 TaskModeBar 统计
          setSelectedVideo((prev) => (prev && prev.id === currentVideoId ? { ...prev, clips: validClips } : prev))
          setVideos((prev) => prev.map((v) => (v.id === currentVideoId ? { ...v, clips: validClips } : v)))
        }
      })
      .catch(() => {
        if (!isCancelled) {
          setClips([])
        }
      })
      .finally(() => {
        if (!isCancelled) {
          setIsLoadingClips(false)
        }
      })

    return () => {
      isCancelled = true
    }
  }, [apiBaseUrl, selectedVideo?.id])

  // 片段 CRUD 交互处理
  const handleAddClip = async (payload: ClipSegmentCreatePayload) => {
    if (!selectedVideo) return
    const newClip = await createVideoClip(apiBaseUrl, selectedVideo.id, payload)
    const updatedClips = [...clips, newClip].sort((a, b) => a.order_index - b.order_index)
    setClips(updatedClips)
    setSelectedVideo((prev) => (prev ? { ...prev, clips: updatedClips } : null))
    setVideos((prev) => prev.map((v) => (v.id === selectedVideo.id ? { ...v, clips: updatedClips } : v)))
    setFeedbackNotice({
      type: "success",
      message: `已成功保存片段 #${updatedClips.length}: ${payload.label || `${payload.start_seconds}s - ${payload.end_seconds}s`}`,
    })
  }

  const handleUpdateClip = async (clipId: number, payload: ClipSegmentUpdatePayload) => {
    if (!selectedVideo) return
    const updatedClip = await updateVideoClip(apiBaseUrl, selectedVideo.id, clipId, payload)
    const updatedClips = clips
      .map((c) => (c.id === clipId ? updatedClip : c))
      .sort((a, b) => a.order_index - b.order_index)
    setClips(updatedClips)
    setSelectedVideo((prev) => (prev ? { ...prev, clips: updatedClips } : null))
    setVideos((prev) => prev.map((v) => (v.id === selectedVideo.id ? { ...v, clips: updatedClips } : v)))
    setFeedbackNotice({
      type: "success",
      message: "片段修改已保存",
    })
  }

  const handleDeleteClip = async (clipId: number) => {
    if (!selectedVideo) return
    await deleteVideoClip(apiBaseUrl, selectedVideo.id, clipId)
    const updatedClips = clips.filter((c) => c.id !== clipId)
    setClips(updatedClips)
    setSelectedVideo((prev) => (prev ? { ...prev, clips: updatedClips } : null))
    setVideos((prev) => prev.map((v) => (v.id === selectedVideo.id ? { ...v, clips: updatedClips } : v)))
    setFeedbackNotice({
      type: "success",
      message: "已成功删除片段",
    })
  }

  const handleReorderClips = async (reordered: ClipSegment[]) => {
    if (!selectedVideo) return
    const withNewOrders = reordered.map((clip, index) => ({
      ...clip,
      order_index: index,
    }))
    setClips(withNewOrders)
    setSelectedVideo((prev) => (prev ? { ...prev, clips: withNewOrders } : null))
    setVideos((prev) => prev.map((v) => (v.id === selectedVideo.id ? { ...v, clips: withNewOrders } : v)))

    try {
      await Promise.all(
        withNewOrders.map((clip, index) => {
          const original = clips.find((c) => c.id === clip.id)
          if (original && original.order_index !== index) {
            return updateVideoClip(apiBaseUrl, selectedVideo.id, clip.id, { order_index: index })
          }
          return Promise.resolve()
        })
      )
      setFeedbackNotice({
        type: "success",
        message: "片段顺序已更新",
      })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "更新排序失败"
      setFeedbackNotice({
        type: "error",
        message: `更新片段顺序失败: ${message}`,
      })
    }
  }

  const handleClearAllClips = async () => {
    if (!selectedVideo || clips.length === 0) return
    await Promise.all(clips.map((clip) => deleteVideoClip(apiBaseUrl, selectedVideo.id, clip.id)))
    setClips([])
    setSelectedVideo((prev) => (prev ? { ...prev, clips: [] } : null))
    setVideos((prev) => prev.map((v) => (v.id === selectedVideo.id ? { ...v, clips: [] } : v)))
    setFeedbackNotice({
      type: "success",
      message: "已清空所有片段",
    })
  }

  // 清空片段并提交无需处理决策（满足后端约束并实现可逆操作）
  const handleClearAndRecordNoAction = async () => {
    if (!selectedVideo) return
    setIsSubmittingDecision(true)
    setFeedbackNotice(null)
    try {
      if (clips.length > 0) {
        await Promise.all(clips.map((clip) => deleteVideoClip(apiBaseUrl, selectedVideo.id, clip.id)))
        setClips([])
      }
      const updated = await recordDecision(apiBaseUrl, selectedVideo.id, "no_action")
      const synced: VideoItem = { ...updated, clips: [] }
      setVideos((prev) => prev.map((item) => (item.id === synced.id ? synced : item)))
      setSelectedVideo(synced)
      setUnprocessedTotal((prev) => Math.max(0, prev - 1))
      setFeedbackNotice({
        type: "success",
        message: `已将「${updated.filename}」成功记录为：无需处理 (No action)`,
      })
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

  const handleSeekVideo = (seconds: number) => {
    setSeekTime(seconds)
  }

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

    // 校验：仅在至少存在 1 个有效片段时允许提交 clip_selected
    if (decision === "clip_selected" && clips.length === 0) {
      setFeedbackNotice({
        type: "error",
        message: "无法提交「片段已选」：请至少在时间轴上添加并保存 1 个有效片段。",
      })
      return
    }

    // 校验：若存在片段，需提示或清空后方可标记 no_action
    if (decision === "no_action" && clips.length > 0) {
      setFeedbackNotice({
        type: "error",
        message: `无法提交「无需处理」：当前视频存在 ${clips.length} 个片段。请先清空或删除所有片段后再标记。`,
      })
      return
    }

    setIsSubmittingDecision(true)
    setFeedbackNotice(null)

    try {
      const updated = await recordDecision(apiBaseUrl, selectedVideo.id, decision)

      // 更新列表内该视频状态
      const synced: VideoItem = { ...updated, clips }
      setVideos((prev) => prev.map((item) => (item.id === synced.id ? synced : item)))
      setSelectedVideo(synced)

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
    void loadVideos(page, statusFilter, pageSize, true)
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
              isRefreshing={isRefreshing}
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

          {/* 右侧：任务模式控制台、视频播放预览与片段时间轴编辑器 */}
          <div className="lg:col-span-5 space-y-4 max-h-[calc(100vh-5rem)] overflow-y-auto pr-1">
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
              seekTime={seekTime}
              onTimeUpdate={setCurrentPlaybackTime}
            />

            {selectedVideo && (
              <ClipTimelineEditor
                video={selectedVideo}
                clips={clips}
                isLoadingClips={isLoadingClips}
                currentTime={currentPlaybackTime}
                onAddClip={handleAddClip}
                onUpdateClip={handleUpdateClip}
                onDeleteClip={handleDeleteClip}
                onReorderClips={handleReorderClips}
                onDecision={handleRecordDecision}
                onClearAndRecordNoAction={handleClearAndRecordNoAction}
                isSubmittingDecision={isSubmittingDecision}
                onSeekVideo={handleSeekVideo}
                onClearAllClips={handleClearAllClips}
              />
            )}
          </div>
        </div>
      </div>
    </AppShell>
  )
}

export default App
