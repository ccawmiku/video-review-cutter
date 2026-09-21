import { ProcessingJob } from "@/types/video"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Scissors,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Ban,
  RotateCcw,
  Sparkles,
} from "lucide-react"

export interface ProcessingJobPanelProps {
  job: ProcessingJob | null
  isStarting?: boolean
  onStartProcessing: () => Promise<void>
  onCancelProcessing?: () => Promise<void>
  canStart: boolean
  videoStatus?: string
  clipCount?: number
  className?: string
}

export function ProcessingJobPanel({
  job,
  isStarting = false,
  onStartProcessing,
  onCancelProcessing,
  canStart,
  videoStatus,
  clipCount = 0,
  className = "",
}: ProcessingJobPanelProps) {
  const isJobActive = job?.status === "pending" || job?.status === "running"
  const percent = job ? Math.round(Math.min(1, Math.max(0, job.progress)) * 100) : 0

  // 渲染任务状态徽章
  const renderStatusBadge = (status: ProcessingJob["status"]) => {
    switch (status) {
      case "pending":
        return (
          <Badge variant="outline" className="gap-1 border-amber-500/40 text-amber-600 bg-amber-50/50 dark:bg-amber-950/20">
            <Clock className="h-3 w-3" />
            <span>排队中 (Pending)</span>
          </Badge>
        )
      case "running":
        return (
          <Badge variant="default" className="gap-1 bg-blue-600 hover:bg-blue-600 text-white animate-pulse">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>剪辑处理中 (Processing)</span>
          </Badge>
        )
      case "completed":
        return (
          <Badge variant="success" className="gap-1">
            <CheckCircle2 className="h-3 w-3" />
            <span>处理完成 (Completed)</span>
          </Badge>
        )
      case "failed":
        return (
          <Badge variant="destructive" className="gap-1">
            <AlertCircle className="h-3 w-3" />
            <span>处理失败 (Failed)</span>
          </Badge>
        )
      case "cancelled":
        return (
          <Badge variant="secondary" className="gap-1">
            <Ban className="h-3 w-3" />
            <span>已取消 (Cancelled)</span>
          </Badge>
        )
    }
  }

  // 格式化策略说明
  const formatStrategy = (strategy?: string | null) => {
    if (!strategy) return null
    if (strategy === "stream_copy_concat") return "无损流复制快速拼接"
    if (strategy === "reencode_concat") return "全量转码拼接"
    return strategy
  }

  // 仅在已选片段状态、已存在任务、或视频已替换时展示
  const shouldShow = videoStatus === "clip_selected" || job !== null || videoStatus === "replaced"
  if (!shouldShow && clipCount === 0) {
    return null
  }

  return (
    <div
      className={`rounded-lg border bg-card p-3 shadow-xs space-y-3 transition-all ${className}`}
      data-testid="processing-job-panel"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Scissors className="h-4 w-4 text-emerald-600" />
          <h4 className="text-xs font-semibold text-foreground">
            视频剪辑执行与归档替换 (Clip Processing)
          </h4>
        </div>
        {job && <div data-testid="job-status-badge">{renderStatusBadge(job.status)}</div>}
      </div>

      {/* 任务进度展示卡片 */}
      {job && (
        <div className="space-y-2 rounded-md bg-muted/40 p-2.5 text-xs border border-border/50">
          <div className="flex items-center justify-between text-muted-foreground font-mono text-[11px]">
            <span className="flex items-center gap-1.5 truncate">
              {job.strategy && (
                <span className="rounded bg-background px-1.5 py-0.5 border text-foreground font-sans">
                  {formatStrategy(job.strategy)}
                </span>
              )}
              <span className="truncate">任务 #{job.id}</span>
            </span>
            <span
              className="font-bold text-foreground text-xs"
              data-testid="job-progress-percent"
            >
              {percent}%
            </span>
          </div>

          {/* 进度条轨道与进度指示 */}
          <div
            className="w-full bg-muted rounded-full h-2 overflow-hidden"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="剪辑处理进度"
          >
            <div
              className={`h-full transition-all duration-300 rounded-full ${
                job.status === "failed"
                  ? "bg-destructive"
                  : job.status === "completed"
                  ? "bg-emerald-500"
                  : "bg-blue-600"
              }`}
              style={{ width: `${percent}%` }}
              data-testid="job-progress-bar-inner"
            />
          </div>

          {/* 状态阶段消息描述 */}
          <div className="flex items-center justify-between text-[11px] pt-0.5">
            <span
              className={`truncate ${
                job.status === "failed" ? "text-destructive font-medium" : "text-muted-foreground"
              }`}
              data-testid="job-message"
            >
              {job.message || (isJobActive ? "正在执行剪辑流水线..." : "就绪")}
            </span>
            {job.started_at && (
              <span className="text-[10px] text-muted-foreground font-mono shrink-0 ml-2">
                {new Date(job.updated_at).toLocaleTimeString()}
              </span>
            )}
          </div>

          {/* 错误详情提示 */}
          {job.status === "failed" && job.error && (
            <div
              className="rounded bg-destructive/10 border border-destructive/20 p-2 text-destructive text-[11px] flex items-start gap-1.5"
              data-testid="job-error"
            >
              <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <span className="break-all">{job.error}</span>
            </div>
          )}

          {/* 替换成功提示 */}
          {job.status === "completed" && (
            <div
              className="rounded bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-500/20 p-2 text-emerald-700 dark:text-emerald-400 text-[11px] flex items-center gap-1.5"
              data-testid="job-completed-notice"
            >
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              <span>已成功按选定片段生成新视频，原视频已安全移动至归档目录，并完成原地替换。</span>
            </div>
          )}
        </div>
      )}

      {/* 控制操作按钮区域 */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <div className="flex items-center gap-2">
          {(!job || job.status === "completed" || job.status === "failed" || job.status === "cancelled") && (
            <Button
              type="button"
              variant="default"
              size="sm"
              disabled={isStarting || !canStart}
              onClick={onStartProcessing}
              className={`gap-1.5 text-xs font-medium ${
                canStart
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs"
                  : "opacity-60 cursor-not-allowed"
              }`}
              aria-label="开始剪辑与替换"
              data-testid="start-processing-btn"
            >
              {isStarting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : job?.status === "completed" || job?.status === "failed" ? (
                <RotateCcw className="h-3.5 w-3.5" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              <span>
                {isStarting
                  ? "正在启动任务..."
                  : job?.status === "completed"
                  ? "重新执行剪辑"
                  : job?.status === "failed"
                  ? "重试剪辑处理"
                  : "开始剪辑与替换 (Start Processing)"}
              </span>
            </Button>
          )}

          {isJobActive && (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="default"
                size="sm"
                disabled
                className="gap-1.5 text-xs bg-blue-600 text-white cursor-not-allowed"
                data-testid="processing-active-indicator"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>正在执行剪辑...</span>
              </Button>

              {onCancelProcessing && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onCancelProcessing}
                  className="gap-1 text-xs text-muted-foreground hover:text-destructive"
                  data-testid="cancel-job-btn"
                >
                  <Ban className="h-3 w-3" />
                  <span>取消</span>
                </Button>
              )}
            </div>
          )}

          {!canStart && !isJobActive && videoStatus !== "clip_selected" && (
            <span className="text-[11px] text-muted-foreground">
              请先在时间轴上设置片段并提交「片段已选」后再执行剪辑
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
export default ProcessingJobPanel
