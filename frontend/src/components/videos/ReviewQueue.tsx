import { VideoItem, VideoStatus } from "@/types/video"
import { StatusBadge } from "./StatusBadge"
import { formatDuration, formatFileSize, formatResolution } from "@/lib/formatters"
import { Button } from "@/components/ui/button"
import {
  ChevronLeft,
  ChevronRight,
  Sparkles,
  RefreshCw,
  Clock,
  Layers,
  Film,
  AlertCircle,
  FolderOpen,
} from "lucide-react"

interface ReviewQueueProps {
  videos: VideoItem[]
  selectedVideoId: number | null
  currentStatusFilter: VideoStatus | "all"
  page: number
  pageSize: number
  total: number
  totalPages: number
  unprocessedCount: number
  isLoading: boolean
  error: string | null
  isTaskMode: boolean
  onSelectVideo: (video: VideoItem) => void
  onFilterChange: (status: VideoStatus | "all") => void
  onPageChange: (newPage: number) => void
  onPageSizeChange: (newPageSize: number) => void
  onRefresh: () => void
  onStartTaskMode: () => void
}

const statusFilterTabs: Array<{ id: VideoStatus | "all"; label: string }> = [
  { id: "all", label: "全部" },
  { id: "unprocessed", label: "未处理" },
  { id: "no_action", label: "无需处理" },
  { id: "clip_selected", label: "片段已选" },
  { id: "discarded", label: "已废弃" },
  { id: "replaced", label: "已替换" },
]

export function ReviewQueue({
  videos,
  selectedVideoId,
  currentStatusFilter,
  page,
  pageSize,
  total,
  totalPages,
  unprocessedCount,
  isLoading,
  error,
  isTaskMode,
  onSelectVideo,
  onFilterChange,
  onPageChange,
  onPageSizeChange,
  onRefresh,
  onStartTaskMode,
}: ReviewQueueProps) {
  return (
    <section
      aria-label="视频审核队列"
      className="flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-sm"
    >
      {/* 队列控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Layers className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold tracking-tight text-foreground flex items-center gap-2">
              视频评审队列 (Review Queue)
              <span className="text-xs font-normal text-muted-foreground">
                (共 {total} 部 · 待处理 {unprocessedCount} 部)
              </span>
            </h2>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" aria-hidden="true" />
                默认按时长降序 (Duration Descending)
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={isLoading}
            className="h-8 gap-1 text-xs"
            aria-label="刷新视频列表"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} aria-hidden="true" />
            <span>刷新</span>
          </Button>

          <Button
            variant={isTaskMode ? "secondary" : "default"}
            size="sm"
            onClick={onStartTaskMode}
            disabled={unprocessedCount === 0 || isLoading}
            className="h-8 gap-1.5 text-xs font-medium"
            aria-label={
              unprocessedCount === 0
                ? "暂无待处理视频"
                : "进入任务模式开始连续审核"
            }
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{isTaskMode ? "任务模式进行中" : `任务模式 (${unprocessedCount})`}</span>
          </Button>
        </div>
      </div>

      {/* 状态筛选标签栏 */}
      <div
        className="flex flex-wrap items-center gap-1.5"
        role="tablist"
        aria-label="按审核状态筛选"
      >
        {statusFilterTabs.map((tab) => {
          const isActive = currentStatusFilter === tab.id
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => onFilterChange(tab.id)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                isActive
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* 列表主体内容：加载、错误、空状态与数据列表 */}
      <div className="min-h-[320px]">
        {isLoading ? (
          <div
            className="flex flex-col items-center justify-center p-12 text-center"
            role="status"
            aria-live="polite"
          >
            <RefreshCw className="h-8 w-8 animate-spin text-primary mb-2" aria-hidden="true" />
            <p className="text-sm font-medium text-foreground">正在加载视频列表...</p>
            <p className="text-xs text-muted-foreground mt-1">
              通过 GET /api/videos 获取排序后的视频目录
            </p>
          </div>
        ) : error ? (
          <div
            className="flex flex-col items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5 p-8 text-center"
            role="alert"
          >
            <AlertCircle className="h-8 w-8 text-destructive mb-2" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-destructive">加载视频队列出错</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-md">{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={onRefresh}
              className="mt-3 text-xs"
            >
              重新重试
            </Button>
          </div>
        ) : videos.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center rounded-lg border border-dashed p-10 text-center bg-muted/20"
            role="status"
          >
            <FolderOpen className="h-10 w-10 text-muted-foreground/40 mb-2" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-foreground">暂无符合条件的视频</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              {currentStatusFilter !== "all"
                ? `当前筛选状态「${statusFilterTabs.find((t) => t.id === currentStatusFilter)?.label}」下未找到视频记录。`
                : "存储根目录下暂未扫描到视频文件，请确认 backend 扫描服务配置。"}
            </p>
            {currentStatusFilter !== "all" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onFilterChange("all")}
                className="mt-3 text-xs"
              >
                清除状态筛选
              </Button>
            )}
          </div>
        ) : (
          <ul
            className="divide-y rounded-lg border bg-background"
            role="list"
            aria-label="视频条目列表"
          >
            {videos.map((video) => {
              const isSelected = selectedVideoId === video.id
              return (
                <li
                  key={video.id}
                  className={`group flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 text-left transition-colors hover:bg-accent/40 focus-within:bg-accent/50 ${
                    isSelected ? "bg-accent/70 border-l-4 border-l-primary" : ""
                  }`}
                >
                  {/* 点击选择按钮（语义化交互） */}
                  <button
                    type="button"
                    onClick={() => onSelectVideo(video)}
                    className="flex flex-1 flex-col sm:flex-row sm:items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded p-1"
                    aria-label={`选择视频 ${video.filename}, 时长 ${formatDuration(video.duration)}, 状态 ${video.status}`}
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                      <Film className="h-4 w-4" aria-hidden="true" />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground truncate max-w-xs sm:max-w-md">
                          {video.filename}
                        </span>
                        {isSelected && (
                          <span className="rounded bg-primary/20 text-primary px-1.5 py-0.2 text-[10px] font-medium shrink-0">
                            正在预览
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground mt-0.5">
                        <span className="font-mono font-medium text-foreground">
                          {formatDuration(video.duration)}
                        </span>
                        <span>{formatResolution(video.width, video.height)}</span>
                        <span>{video.codec ? video.codec.toUpperCase() : "--"}</span>
                        {video.fps && <span>{video.fps.toFixed(1)} fps</span>}
                        <span>{formatFileSize(video.size)}</span>
                      </div>
                    </div>
                  </button>

                  {/* 状态徽章与快捷操作 */}
                  <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                    <StatusBadge status={video.status} />
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* 分页控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <span>
            第 <span className="font-medium text-foreground">{page}</span> /{" "}
            <span className="font-medium text-foreground">{totalPages || 1}</span> 页
          </span>
          <span>(每页</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded border bg-background px-1.5 py-0.5 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            aria-label="每页显示条数"
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>
          <span>条)</span>
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1 || isLoading}
            className="h-8 gap-1 text-xs"
            aria-label="上一页"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            <span>上一页</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages || isLoading}
            className="h-8 gap-1 text-xs"
            aria-label="下一页"
          >
            <span>下一页</span>
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </section>
  )
}
