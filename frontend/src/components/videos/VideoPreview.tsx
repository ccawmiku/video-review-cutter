import * as React from "react"
import { VideoItem } from "@/types/video"
import { getVideoPreviewUrl } from "@/api/videoClient"
import { formatDuration, formatFileSize, formatResolution } from "@/lib/formatters"
import { StatusBadge } from "./StatusBadge"
import { Film, AlertTriangle, RefreshCw, Info } from "lucide-react"
import { Button } from "@/components/ui/button"

interface VideoPreviewProps {
  video: VideoItem | null
  apiBaseUrl: string
  className?: string
  seekTime?: number | null
  seekNonce?: number
  onTimeUpdate?: (currentTime: number) => void
}

export function VideoPreview({
  video,
  apiBaseUrl,
  className = "",
  seekTime = null,
  seekNonce,
  onTimeUpdate,
}: VideoPreviewProps) {
  const [hasError, setHasError] = React.useState(false)
  const [retryKey, setRetryKey] = React.useState(0)
  const videoRef = React.useRef<HTMLVideoElement>(null)

  React.useEffect(() => {
    setHasError(false)
  }, [video?.id, retryKey])

  React.useEffect(() => {
    if (videoRef.current && seekTime != null && Number.isFinite(seekTime)) {
      videoRef.current.currentTime = seekTime
      if (typeof videoRef.current.pause === "function") {
        try {
          videoRef.current.pause()
        } catch {
          // ignore playback state errors
        }
      }
    }
  }, [seekTime, seekNonce])

  if (!video) {
    return (
      <div
        className={`flex flex-col items-center justify-center p-12 text-center rounded-xl border border-dashed bg-muted/20 min-h-[360px] ${className}`}
        data-testid="video-preview-empty"
      >
        <Film className="h-12 w-12 text-muted-foreground/50 mb-3" aria-hidden="true" />
        <h3 className="text-base font-semibold text-foreground">未选择预览视频</h3>
        <p className="text-xs text-muted-foreground max-w-sm mt-1">
          从视频列表中点击任一项，或进入任务模式开始逐个预览与审核。
        </p>
      </div>
    )
  }

  const previewUrl = getVideoPreviewUrl(apiBaseUrl, video.id)

  const handleRetry = () => {
    setHasError(false)
    setRetryKey((prev) => prev + 1)
  }

  return (
    <div
      className={`flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-sm ${className}`}
      data-testid="video-preview-card"
    >
      {/* 头部信息 */}
      <div className="flex flex-wrap items-start justify-between gap-2 border-b pb-3">
        <div className="min-w-0 flex-1">
          <h3
            className="text-base font-semibold text-foreground truncate"
            title={video.filename}
          >
            {video.filename}
          </h3>
          <p className="text-xs text-muted-foreground font-mono truncate mt-0.5" title={video.path}>
            {video.path}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <StatusBadge status={video.status} />
        </div>
      </div>

      {/* 视频播放器区域 */}
      <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black flex items-center justify-center">
        {hasError ? (
          <div
            className="flex flex-col items-center justify-center p-6 text-center text-slate-200"
            role="alert"
          >
            <AlertTriangle className="h-10 w-10 text-amber-400 mb-2" aria-hidden="true" />
            <p className="text-sm font-medium">无法加载视频流预览</p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              后端预览服务可能无法读取该文件，或媒体编码格式需要转码。
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRetry}
              className="mt-4 gap-1.5 text-xs bg-white/10 hover:bg-white/20 border-white/20 text-white"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              重新尝试加载
            </Button>
          </div>
        ) : (
          <video
            ref={videoRef}
            key={`${video.id}-${retryKey}`}
            src={previewUrl}
            controls
            preload="metadata"
            className="h-full w-full object-contain"
            aria-label={`预览播放器: ${video.filename}`}
            onError={() => setHasError(true)}
            onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
            data-testid="video-preview-player"
          >
            您的浏览器不支持 HTML5 video 视频预览播放。
          </video>
        )}
      </div>

      {/* 媒体元数据展示 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 rounded-lg bg-muted/40 p-3 text-xs">
        <div>
          <span className="text-muted-foreground block">视频时长</span>
          <span className="font-medium font-mono text-foreground">
            {formatDuration(video.duration)}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground block">分辨率</span>
          <span className="font-medium text-foreground">
            {formatResolution(video.width, video.height)}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground block">编码与帧率</span>
          <span className="font-medium text-foreground">
            {video.codec ? video.codec.toUpperCase() : "--"}
            {video.fps ? ` · ${video.fps.toFixed(1)} fps` : ""}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground block">文件大小</span>
          <span className="font-medium font-mono text-foreground">
            {formatFileSize(video.size)}
          </span>
        </div>
      </div>

      {/* 提示信息 */}
      {video.scan_error && (
        <div
          className="flex items-start gap-2 rounded-md bg-amber-500/10 border border-amber-500/20 p-2.5 text-xs text-amber-700 dark:text-amber-400"
          role="note"
        >
          <Info className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <span className="font-semibold">元数据探测提示: </span>
            <span>{video.scan_error}</span>
          </div>
        </div>
      )}
    </div>
  )
}
