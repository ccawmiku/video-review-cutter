import { VideoItem, ReviewDecision } from "@/types/video"
import { Button } from "@/components/ui/button"
import {
  CheckCheck,
  Scissors,
  SkipForward,
  X,
  Sparkles,
  HelpCircle,
  Loader2,
} from "lucide-react"

interface TaskModeBarProps {
  currentVideo: VideoItem | null
  unprocessedCount: number
  currentIndex: number
  totalUnprocessed: number
  isSubmitting: boolean
  onDecision: (decision: ReviewDecision) => void
  onSkip: () => void
  onExit: () => void
}

export function TaskModeBar({
  currentVideo,
  unprocessedCount,
  currentIndex,
  totalUnprocessed,
  isSubmitting,
  onDecision,
  onSkip,
  onExit,
}: TaskModeBarProps) {
  const clipCount = currentVideo?.clips?.length ?? 0
  const canSelectClips = clipCount > 0

  return (
    <div
      className="flex flex-col gap-3 rounded-xl border bg-gradient-to-r from-primary/5 via-primary/10 to-primary/5 p-4 shadow-sm"
      role="region"
      aria-label="任务模式决策面板"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-primary/20 pb-2.5">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h4 className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
              任务模式 (Task Mode)
              <span className="rounded bg-primary/20 px-1.5 py-0.5 text-[11px] font-normal text-primary">
                自动推进待处理项
              </span>
            </h4>
            <p className="text-xs text-muted-foreground">
              {currentVideo
                ? `审核中: ${currentVideo.filename}`
                : "所有待处理视频已完成审核"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-xs text-muted-foreground">
            待处理项: <span className="font-semibold text-foreground">{unprocessedCount}</span> 部
            {totalUnprocessed > 0 && (
              <span className="ml-1 text-[11px] text-muted-foreground">
                (当前进度: {Math.min(currentIndex + 1, totalUnprocessed)} / {totalUnprocessed})
              </span>
            )}
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={onExit}
            className="h-8 gap-1 text-xs hover:bg-background/80"
            aria-label="退出任务模式"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            <span>退出</span>
          </Button>
        </div>
      </div>

      {/* 操作按钮组 */}
      {currentVideo ? (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex flex-wrap items-center gap-2">
            {/* 决策 1: 无需处理 (No action) */}
            <Button
              variant="default"
              size="sm"
              disabled={isSubmitting}
              onClick={() => onDecision("no_action")}
              className="gap-1.5 font-medium bg-blue-600 hover:bg-blue-700 text-white"
              aria-label="标记为无需处理 (No action) 并进入下一个待处理视频"
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <CheckCheck className="h-4 w-4" aria-hidden="true" />
              )}
              <span>无需处理 (No action)</span>
            </Button>

            {/* 决策 2: 片段已选 (Clip selected) */}
            <div className="relative inline-flex items-center">
              <Button
                variant={canSelectClips ? "default" : "outline"}
                size="sm"
                disabled={!canSelectClips || isSubmitting}
                onClick={() => canSelectClips && onDecision("clip_selected")}
                className={`gap-1.5 font-medium ${
                  canSelectClips
                    ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                    : "border-dashed text-muted-foreground cursor-not-allowed opacity-60"
                }`}
                aria-label={
                  canSelectClips
                    ? "确认片段已选 (Clip selected)"
                    : "片段已选 (需先通过时间轴编辑器选定片段)"
                }
                title={
                  canSelectClips
                    ? `已选 ${clipCount} 个片段`
                    : "暂不可用：当前视频暂无裁剪片段（时间轴交互将在后续 Issue 中支持）"
                }
              >
                <Scissors className="h-4 w-4" aria-hidden="true" />
                <span>片段已选 (Clip selected)</span>
                {canSelectClips && (
                  <span className="ml-1 rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                    {clipCount}
                  </span>
                )}
              </Button>
            </div>

            {/* 清晰的状态说明 */}
            {!canSelectClips && (
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground bg-background/50 px-2 py-1 rounded border">
                <HelpCircle className="h-3 w-3 text-muted-foreground/70" aria-hidden="true" />
                <span>需至少 1 个片段（待时间轴 UI 支持）</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={isSubmitting}
              onClick={onSkip}
              className="gap-1 text-xs"
              aria-label="跳过当前视频，查看下一个待处理视频"
            >
              <SkipForward className="h-3.5 w-3.5" aria-hidden="true" />
              <span>跳过 (Skip)</span>
            </Button>
          </div>
        </div>
      ) : (
        <div className="py-2 text-center text-xs text-muted-foreground">
          队列中已无未处理视频，您可以退出任务模式或重新刷新视频目录。
        </div>
      )}
    </div>
  )
}
