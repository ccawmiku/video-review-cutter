import * as React from "react"
import { ClipSegment, ClipSegmentCreatePayload, ClipSegmentUpdatePayload, ReviewDecision, VideoItem } from "@/types/video"
import { validateClipBounds } from "@/lib/clipValidation"
import { formatDuration } from "@/lib/formatters"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Scissors,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  Play,
  CheckCheck,
  RotateCcw,
  Clock,
  Tag,
  FileText,
  HelpCircle,
  Loader2,
  SlidersHorizontal,
} from "lucide-react"

export interface ClipTimelineEditorProps {
  video: VideoItem
  clips: ClipSegment[]
  isLoadingClips?: boolean
  currentTime?: number
  onAddClip: (payload: ClipSegmentCreatePayload) => Promise<void>
  onUpdateClip: (clipId: number, payload: ClipSegmentUpdatePayload) => Promise<void>
  onDeleteClip: (clipId: number) => Promise<void>
  onReorderClips: (reorderedClips: ClipSegment[]) => Promise<void>
  onDecision?: (decision: ReviewDecision) => Promise<void>
  onClearAndRecordNoAction?: () => Promise<void>
  isSubmittingDecision?: boolean
  onSeekVideo?: (seconds: number) => void
  onClearAllClips?: () => Promise<void>
  className?: string
}

export function ClipTimelineEditor({
  video,
  clips: rawClips,
  isLoadingClips = false,
  currentTime,
  onAddClip,
  onUpdateClip,
  onDeleteClip,
  onReorderClips,
  onDecision,
  onClearAndRecordNoAction,
  isSubmittingDecision = false,
  onSeekVideo,
  onClearAllClips,
  className = "",
}: ClipTimelineEditorProps) {
  const clips = React.useMemo(() => (Array.isArray(rawClips) ? rawClips : []), [rawClips])
  const duration = video.duration && video.duration > 0 ? video.duration : 60

  // 正在编辑的片段状态，null 表示无
  const [editingClipId, setEditingClipId] = React.useState<number | null>(null)
  const [editStart, setEditStart] = React.useState<string>("")
  const [editEnd, setEditEnd] = React.useState<string>("")
  const [editLabel, setEditLabel] = React.useState<string>("")
  const [editNote, setEditNote] = React.useState<string>("")
  const [isSavingEdit, setIsSavingEdit] = React.useState<boolean>(false)

  // 新增片段表单状态
  const [isAdding, setIsAdding] = React.useState<boolean>(false)
  const [newStart, setNewStart] = React.useState<string>("0")
  const [newEnd, setNewEnd] = React.useState<string>(
    video.duration ? Math.min(10, video.duration).toString() : "10"
  )
  const [newLabel, setNewLabel] = React.useState<string>("")
  const [newNote, setNewNote] = React.useState<string>("")
  const [isCreating, setIsCreating] = React.useState<boolean>(false)
  const [showClearConfirm, setShowClearConfirm] = React.useState<boolean>(false)

  // 选中的高亮片段
  const [selectedClipId, setSelectedClipId] = React.useState<number | null>(null)

  // 新增片段校验
  const newStartNum = parseFloat(newStart)
  const newEndNum = parseFloat(newEnd)
  const newValidation = React.useMemo(() => {
    return validateClipBounds(newStartNum, newEndNum, video.duration)
  }, [newStartNum, newEndNum, video.duration])

  // 编辑片段校验
  const editStartNum = parseFloat(editStart)
  const editEndNum = parseFloat(editEnd)
  const editValidation = React.useMemo(() => {
    return validateClipBounds(editStartNum, editEndNum, video.duration)
  }, [editStartNum, editEndNum, video.duration])

  // 自动填充新增片段的默认值
  const handleOpenAdd = () => {
    let startVal = 0
    if (currentTime != null && currentTime >= 0 && (!video.duration || currentTime < video.duration)) {
      startVal = Math.round(currentTime * 10) / 10
    } else if (clips.length > 0) {
      const maxEnd = Math.max(...clips.map((c) => c.end_seconds))
      if (!video.duration || maxEnd < video.duration) {
        startVal = maxEnd
      }
    }
    const endVal = video.duration
      ? Math.min(Math.round((startVal + 10) * 10) / 10, video.duration)
      : startVal + 10

    setNewStart(startVal.toString())
    setNewEnd(endVal.toString())
    setNewLabel("")
    setNewNote("")
    setIsAdding(true)
  }

  // 提交新增片段
  const handleSaveNew = async () => {
    if (!newValidation.isValid) return
    setIsCreating(true)
    try {
      await onAddClip({
        start_seconds: newStartNum,
        end_seconds: newEndNum,
        label: newLabel.trim() || null,
        note: newNote.trim() || null,
        order_index: clips.length,
      })
      setIsAdding(false)
      setNewLabel("")
      setNewNote("")
    } finally {
      setIsCreating(false)
    }
  }

  // 开启编辑
  const handleStartEdit = (clip: ClipSegment) => {
    setEditingClipId(clip.id)
    setSelectedClipId(clip.id)
    setEditStart(clip.start_seconds.toString())
    setEditEnd(clip.end_seconds.toString())
    setEditLabel(clip.label || "")
    setEditNote(clip.note || "")
  }

  // 提交编辑
  const handleSaveEdit = async () => {
    if (editingClipId == null || !editValidation.isValid) return
    setIsSavingEdit(true)
    try {
      await onUpdateClip(editingClipId, {
        start_seconds: editStartNum,
        end_seconds: editEndNum,
        label: editLabel.trim() || null,
        note: editNote.trim() || null,
      })
      setEditingClipId(null)
    } finally {
      setIsSavingEdit(false)
    }
  }

  // 取消编辑
  const handleCancelEdit = () => {
    setEditingClipId(null)
  }

  // 上移片段
  const handleMoveUp = async (index: number) => {
    if (index <= 0) return
    const updated = [...clips]
    const temp = updated[index]
    updated[index] = updated[index - 1]
    updated[index - 1] = temp
    await onReorderClips(updated)
  }

  // 下移片段
  const handleMoveDown = async (index: number) => {
    if (index >= clips.length - 1) return
    const updated = [...clips]
    const temp = updated[index]
    updated[index] = updated[index + 1]
    updated[index + 1] = temp
    await onReorderClips(updated)
  }

  // 时间轴点击：跳转并可设置高亮
  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const clickRatio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    const clickedSeconds = Math.round(clickRatio * duration * 10) / 10
    onSeekVideo?.(clickedSeconds)
  }

  // 微调数字辅助函数
  const adjustValue = (
    currentStr: string,
    delta: number,
    setter: (val: string) => void,
    min = 0,
    max = video.duration ?? Infinity
  ) => {
    const current = parseFloat(currentStr) || 0
    const next = Math.max(min, Math.min(max, Math.round((current + delta) * 10) / 10))
    setter(next.toString())
  }

  const totalClipsDuration = React.useMemo(() => {
    return clips.reduce((acc, c) => acc + Math.max(0, c.end_seconds - c.start_seconds), 0)
  }, [clips])

  return (
    <section
      aria-label="片段时间轴编辑器"
      className={`flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-sm ${className}`}
      data-testid="clip-timeline-editor"
    >
      {/* 头部标题与片段统计 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <Scissors className="h-4 w-4" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
              片段时间轴编辑器 (Clip Timeline)
              <Badge variant="secondary" className="text-[11px] font-normal">
                {clips.length} 个片段
              </Badge>
            </h3>
            <p className="text-xs text-muted-foreground flex items-center gap-2">
              <span>已选总时长: {Math.round(totalClipsDuration * 10) / 10}s</span>
              <span>·</span>
              <span>视频总长: {formatDuration(video.duration)}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isAdding && (
            <Button
              variant="default"
              size="sm"
              onClick={handleOpenAdd}
              className="h-8 gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
              aria-label="添加新片段"
              data-testid="add-clip-button"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              <span>添加片段</span>
            </Button>
          )}
        </div>
      </div>

      {/* 可视化持续时间轴与范围标记 (Visual Timeline) */}
      <div className="space-y-1.5" data-testid="clip-visual-timeline">
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="font-mono">0:00 (0.0s)</span>
          <span className="font-mono">{formatDuration(duration / 2)}</span>
          <span className="font-mono">
            {formatDuration(video.duration)} ({Math.round(duration * 10) / 10}s)
          </span>
        </div>

        {/* 时间轴轨道 */}
        <div
          role="region"
          aria-label="可视化时长轴交互轨道，点击可跳转视频进度"
          onClick={handleTimelineClick}
          className="relative h-10 w-full rounded-lg bg-muted/60 border border-input/60 overflow-hidden cursor-pointer select-none shadow-inner"
        >
          {/* 背景刻度标线 */}
          <div className="absolute inset-0 flex justify-between pointer-events-none opacity-20">
            <div className="border-r border-foreground h-full" />
            <div className="border-r border-foreground h-full" />
            <div className="border-r border-foreground h-full" />
            <div className="border-r border-foreground h-full" />
            <div className="border-r border-foreground h-full" />
          </div>

          {/* 各裁剪片段范围标记 (Marker Ranges) */}
          {clips.map((clip, index) => {
            const leftPct = Math.max(0, Math.min(100, (clip.start_seconds / duration) * 100))
            const widthPct = Math.max(
              0.8,
              Math.min(100 - leftPct, ((clip.end_seconds - clip.start_seconds) / duration) * 100)
            )
            const isSelected = selectedClipId === clip.id || editingClipId === clip.id

            return (
              <div
                key={clip.id}
                role="button"
                tabIndex={0}
                data-testid={`timeline-marker-${clip.id}`}
                aria-label={`片段 #${index + 1}: ${clip.label || "未命名"} (${clip.start_seconds}s 至 ${clip.end_seconds}s)`}
                onClick={(e) => {
                  e.stopPropagation()
                  setSelectedClipId(clip.id)
                  onSeekVideo?.(clip.start_seconds)
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    e.stopPropagation()
                    setSelectedClipId(clip.id)
                    onSeekVideo?.(clip.start_seconds)
                  }
                }}
                style={{
                  left: `${leftPct}%`,
                  width: `${widthPct}%`,
                }}
                className={`absolute top-1 bottom-1 rounded flex items-center justify-center text-[10px] font-semibold transition-all border shadow-sm cursor-pointer overflow-hidden z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  isSelected
                    ? "bg-emerald-500 text-white border-emerald-400 ring-2 ring-emerald-400 z-20"
                    : "bg-emerald-500/35 hover:bg-emerald-500/50 text-emerald-950 dark:text-emerald-100 border-emerald-500/50"
                }`}
                title={`#${index + 1} ${clip.label || "片段"}: ${clip.start_seconds}s - ${clip.end_seconds}s (${Math.round((clip.end_seconds - clip.start_seconds) * 10) / 10}s)`}
              >
                <span className="truncate px-1 pointer-events-none">
                  #{index + 1} {clip.label ? `· ${clip.label}` : ""}
                </span>
              </div>
            )
          })}

          {/* 当前视频播放针 (Playhead) */}
          {currentTime != null && currentTime >= 0 && (
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-rose-500 z-30 pointer-events-none transition-all duration-75 shadow-sm"
              style={{
                left: `${Math.max(0, Math.min(100, (currentTime / duration) * 100))}%`,
              }}
              title={`当前播放时间: ${currentTime.toFixed(1)}s`}
            >
              <div className="w-2 h-2 -ml-[3px] bg-rose-500 rounded-full" />
            </div>
          )}
        </div>
      </div>

      {/* 新增片段表单 (Add Segment Form) */}
      {isAdding && (
        <div
          className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 space-y-3"
          data-testid="add-clip-form"
          role="group"
          aria-label="新增片段表单"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              创建新片段
            </span>
            {currentTime != null && currentTime >= 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const rounded = Math.round(currentTime * 10) / 10
                  setNewStart(rounded.toString())
                  if (newEndNum <= rounded) {
                    setNewEnd(Math.min(rounded + 5, video.duration ?? rounded + 5).toString())
                  }
                }}
                className="h-6 text-[11px] text-muted-foreground hover:text-foreground px-2"
                aria-label="将当前播放位置设为起始时间"
              >
                当前时间 ({currentTime.toFixed(1)}s) 设为起点
              </Button>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* 起始时间控制 */}
            <div className="space-y-1">
              <label
                htmlFor="new-clip-start-input"
                className="text-xs font-medium text-foreground flex items-center gap-1"
              >
                <Clock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                起始时间 (秒)
              </label>
              <div className="flex items-center gap-1">
                <input
                  id="new-clip-start-input"
                  type="number"
                  step="0.1"
                  min="0"
                  max={video.duration ?? undefined}
                  value={newStart}
                  onChange={(e) => setNewStart(e.target.value)}
                  className="w-full rounded border bg-background px-2.5 py-1 text-xs font-mono text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  aria-label="起始时间（秒）"
                  data-testid="new-clip-start"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => adjustValue(newStart, -0.1, setNewStart)}
                  className="h-7 w-7 p-0 text-[10px]"
                  aria-label="起始时间减少0.1秒"
                >
                  -0.1
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => adjustValue(newStart, 0.1, setNewStart)}
                  className="h-7 w-7 p-0 text-[10px]"
                  aria-label="起始时间增加0.1秒"
                >
                  +0.1
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => adjustValue(newStart, 1, setNewStart)}
                  className="h-7 w-7 p-0 text-[10px]"
                  aria-label="起始时间增加1秒"
                >
                  +1
                </Button>
              </div>
              {newValidation.errors.start && (
                <p className="text-[11px] text-destructive" role="alert">
                  {newValidation.errors.start}
                </p>
              )}
            </div>

            {/* 结束时间控制 */}
            <div className="space-y-1">
              <label
                htmlFor="new-clip-end-input"
                className="text-xs font-medium text-foreground flex items-center gap-1"
              >
                <Clock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                结束时间 (秒)
              </label>
              <div className="flex items-center gap-1">
                <input
                  id="new-clip-end-input"
                  type="number"
                  step="0.1"
                  min="0"
                  max={video.duration ?? undefined}
                  value={newEnd}
                  onChange={(e) => setNewEnd(e.target.value)}
                  className="w-full rounded border bg-background px-2.5 py-1 text-xs font-mono text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  aria-label="结束时间（秒）"
                  data-testid="new-clip-end"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => adjustValue(newEnd, -0.1, setNewEnd)}
                  className="h-7 w-7 p-0 text-[10px]"
                  aria-label="结束时间减少0.1秒"
                >
                  -0.1
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => adjustValue(newEnd, 0.1, setNewEnd)}
                  className="h-7 w-7 p-0 text-[10px]"
                  aria-label="结束时间增加0.1秒"
                >
                  +0.1
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => adjustValue(newEnd, 1, setNewEnd)}
                  className="h-7 w-7 p-0 text-[10px]"
                  aria-label="结束时间增加1秒"
                >
                  +1
                </Button>
              </div>
              {newValidation.errors.end && (
                <p className="text-[11px] text-destructive" role="alert">
                  {newValidation.errors.end}
                </p>
              )}
            </div>

            {/* 标签 */}
            <div className="space-y-1">
              <label
                htmlFor="new-clip-label-input"
                className="text-xs font-medium text-foreground flex items-center gap-1"
              >
                <Tag className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                标签 (可选)
              </label>
              <input
                id="new-clip-label-input"
                type="text"
                placeholder="例如：精彩镜头、开头导语"
                value={newLabel}
                maxLength={255}
                onChange={(e) => setNewLabel(e.target.value)}
                className="w-full rounded border bg-background px-2.5 py-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label="片段标签"
                data-testid="new-clip-label"
              />
            </div>

            {/* 备注 */}
            <div className="space-y-1">
              <label
                htmlFor="new-clip-note-input"
                className="text-xs font-medium text-foreground flex items-center gap-1"
              >
                <FileText className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                备注 (可选)
              </label>
              <input
                id="new-clip-note-input"
                type="text"
                placeholder="例如：保留该段动作剪辑"
                value={newNote}
                maxLength={1024}
                onChange={(e) => setNewNote(e.target.value)}
                className="w-full rounded border bg-background px-2.5 py-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label="片段备注"
                data-testid="new-clip-note"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-1 border-t">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsAdding(false)}
              className="h-7 text-xs"
            >
              取消
            </Button>
            <Button
              type="button"
              variant="default"
              size="sm"
              disabled={!newValidation.isValid || isCreating}
              onClick={handleSaveNew}
              className="h-7 text-xs bg-emerald-600 hover:bg-emerald-700 text-white gap-1"
              data-testid="save-new-clip-button"
            >
              {isCreating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
              <span>保存片段</span>
            </Button>
          </div>
        </div>
      )}

      {/* 片段列表 (Segments List) */}
      <div className="space-y-2" data-testid="clip-segments-list">
        {isLoadingClips ? (
          <div className="flex items-center justify-center p-6 text-xs text-muted-foreground gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>加载片段列表中...</span>
          </div>
        ) : clips.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center p-6 text-center border border-dashed rounded-lg bg-muted/20 text-xs text-muted-foreground"
            data-testid="no-clips-placeholder"
          >
            <SlidersHorizontal className="h-8 w-8 text-muted-foreground/40 mb-1.5" aria-hidden="true" />
            <p className="font-medium text-foreground">暂无裁剪片段</p>
            <p className="text-[11px] mt-0.5 max-w-xs">
              点击上方「添加片段」或在时间轴上快速添加需要保留的视频区间。
            </p>
          </div>
        ) : (
          <ul className="space-y-2" role="list" aria-label="视频裁剪片段条目">
            {clips.map((clip, index) => {
              const isEditing = editingClipId === clip.id
              const isSelected = selectedClipId === clip.id

              if (isEditing) {
                return (
                  <li
                    key={clip.id}
                    className="rounded-lg border-2 border-primary/50 bg-accent/30 p-3 space-y-3"
                    data-testid={`clip-edit-form-${clip.id}`}
                  >
                    <div className="flex items-center justify-between text-xs font-semibold">
                      <span>编辑片段 #{index + 1}</span>
                      <span className="font-mono text-muted-foreground">
                        {editStartNum}s - {editEndNum}s
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {/* 编辑起始时间 */}
                      <div className="space-y-1">
                        <label
                          htmlFor={`edit-clip-start-${clip.id}`}
                          className="text-xs font-medium text-foreground flex items-center gap-1"
                        >
                          <Clock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                          起始时间 (秒)
                        </label>
                        <div className="flex items-center gap-1">
                          <input
                            id={`edit-clip-start-${clip.id}`}
                            type="number"
                            step="0.1"
                            min="0"
                            max={video.duration ?? undefined}
                            value={editStart}
                            onChange={(e) => setEditStart(e.target.value)}
                            className="w-full rounded border bg-background px-2.5 py-1 text-xs font-mono text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                            aria-label={`编辑片段 #${index + 1} 起始时间`}
                            data-testid={`edit-start-input-${clip.id}`}
                          />
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => adjustValue(editStart, -0.1, setEditStart)}
                            className="h-7 w-7 p-0 text-[10px]"
                            aria-label="减少0.1秒"
                          >
                            -0.1
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => adjustValue(editStart, 0.1, setEditStart)}
                            className="h-7 w-7 p-0 text-[10px]"
                            aria-label="增加0.1秒"
                          >
                            +0.1
                          </Button>
                        </div>
                        {editValidation.errors.start && (
                          <p className="text-[11px] text-destructive" role="alert">
                            {editValidation.errors.start}
                          </p>
                        )}
                      </div>

                      {/* 编辑结束时间 */}
                      <div className="space-y-1">
                        <label
                          htmlFor={`edit-clip-end-${clip.id}`}
                          className="text-xs font-medium text-foreground flex items-center gap-1"
                        >
                          <Clock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                          结束时间 (秒)
                        </label>
                        <div className="flex items-center gap-1">
                          <input
                            id={`edit-clip-end-${clip.id}`}
                            type="number"
                            step="0.1"
                            min="0"
                            max={video.duration ?? undefined}
                            value={editEnd}
                            onChange={(e) => setEditEnd(e.target.value)}
                            className="w-full rounded border bg-background px-2.5 py-1 text-xs font-mono text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                            aria-label={`编辑片段 #${index + 1} 结束时间`}
                            data-testid={`edit-end-input-${clip.id}`}
                          />
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => adjustValue(editEnd, -0.1, setEditEnd)}
                            className="h-7 w-7 p-0 text-[10px]"
                            aria-label="减少0.1秒"
                          >
                            -0.1
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => adjustValue(editEnd, 0.1, setEditEnd)}
                            className="h-7 w-7 p-0 text-[10px]"
                            aria-label="增加0.1秒"
                          >
                            +0.1
                          </Button>
                        </div>
                        {editValidation.errors.end && (
                          <p className="text-[11px] text-destructive" role="alert">
                            {editValidation.errors.end}
                          </p>
                        )}
                      </div>

                      {/* 编辑标签 */}
                      <div className="space-y-1">
                        <label
                          htmlFor={`edit-clip-label-${clip.id}`}
                          className="text-xs font-medium text-foreground flex items-center gap-1"
                        >
                          <Tag className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                          标签 (可选)
                        </label>
                        <input
                          id={`edit-clip-label-${clip.id}`}
                          type="text"
                          value={editLabel}
                          maxLength={255}
                          onChange={(e) => setEditLabel(e.target.value)}
                          className="w-full rounded border bg-background px-2.5 py-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                          aria-label={`编辑片段 #${index + 1} 标签`}
                          data-testid={`edit-label-input-${clip.id}`}
                        />
                      </div>

                      {/* 编辑备注 */}
                      <div className="space-y-1">
                        <label
                          htmlFor={`edit-clip-note-${clip.id}`}
                          className="text-xs font-medium text-foreground flex items-center gap-1"
                        >
                          <FileText className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                          备注 (可选)
                        </label>
                        <input
                          id={`edit-clip-note-${clip.id}`}
                          type="text"
                          value={editNote}
                          maxLength={1024}
                          onChange={(e) => setEditNote(e.target.value)}
                          className="w-full rounded border bg-background px-2.5 py-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                          aria-label={`编辑片段 #${index + 1} 备注`}
                          data-testid={`edit-note-input-${clip.id}`}
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-1 border-t">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleCancelEdit}
                        className="h-7 text-xs"
                      >
                        取消
                      </Button>
                      <Button
                        type="button"
                        variant="default"
                        size="sm"
                        disabled={!editValidation.isValid || isSavingEdit}
                        onClick={handleSaveEdit}
                        className="h-7 text-xs bg-primary text-primary-foreground gap-1"
                        data-testid={`save-edit-button-${clip.id}`}
                      >
                        {isSavingEdit ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCheck className="h-3 w-3" />}
                        <span>保存修改</span>
                      </Button>
                    </div>
                  </li>
                )
              }

              return (
                <li
                  key={clip.id}
                  className={`flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 rounded-lg border transition-colors ${
                    isSelected ? "bg-accent/60 border-primary/40 shadow-sm" : "bg-card hover:bg-accent/30"
                  }`}
                  data-testid={`clip-segment-item-${clip.id}`}
                >
                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-xs font-bold font-mono">
                      #{index + 1}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-semibold text-foreground">
                          {clip.start_seconds}s - {clip.end_seconds}s
                        </span>
                        <span className="text-[11px] text-muted-foreground font-mono">
                          (时长: {Math.round((clip.end_seconds - clip.start_seconds) * 10) / 10}s)
                        </span>
                        {clip.label && (
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-normal">
                            {clip.label}
                          </Badge>
                        )}
                      </div>
                      {clip.note && (
                        <p className="text-[11px] text-muted-foreground truncate mt-0.5" title={clip.note}>
                          备注: {clip.note}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* 片段控制工具栏 */}
                  <div className="flex items-center gap-1 shrink-0 self-end sm:self-center">
                    {onSeekVideo && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onSeekVideo(clip.start_seconds)}
                        className="h-7 w-7 p-0"
                        title="定位到片段起点"
                        aria-label={`定位到片段 #${index + 1} 起点`}
                      >
                        <Play className="h-3 w-3" aria-hidden="true" />
                      </Button>
                    )}

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleStartEdit(clip)}
                      className="h-7 px-2 text-xs"
                      aria-label={`编辑片段 #${index + 1}`}
                      data-testid={`edit-clip-button-${clip.id}`}
                    >
                      编辑
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={index === 0}
                      onClick={() => handleMoveUp(index)}
                      className="h-7 w-7 p-0"
                      title="上移片段"
                      aria-label={`上移片段 #${index + 1}`}
                      data-testid={`move-up-clip-${clip.id}`}
                    >
                      <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={index === clips.length - 1}
                      onClick={() => handleMoveDown(index)}
                      className="h-7 w-7 p-0"
                      title="下移片段"
                      aria-label={`下移片段 #${index + 1}`}
                      data-testid={`move-down-clip-${clip.id}`}
                    >
                      <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => onDeleteClip(clip.id)}
                      className="h-7 w-7 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                      title="删除片段"
                      aria-label={`删除片段 #${index + 1}`}
                      data-testid={`delete-clip-${clip.id}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* 评审决策集成操作栏 (Review Decisions: clip_selected & no_action) */}
      <div
        className="rounded-lg border bg-muted/30 p-3 flex flex-col gap-2.5 border-primary/20"
        data-testid="clip-decision-section"
      >
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-foreground">审核决策 (Review Decision):</span>
            {video.status === "clip_selected" ? (
              <Badge variant="success" className="text-[11px]">
                当前已提交: 片段已选 (Clip selected)
              </Badge>
            ) : video.status === "no_action" ? (
              <Badge variant="secondary" className="text-[11px]">
                当前已提交: 无需处理 (No action)
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[11px] text-muted-foreground">
                未处理 (Unprocessed)
              </Badge>
            )}
          </div>

          {clips.length > 0 && onClearAllClips && (
            <div className="flex items-center gap-2">
              {showClearConfirm ? (
                <div className="flex items-center gap-1 text-xs">
                  <span className="text-muted-foreground">确定清空所有片段？</span>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={async () => {
                      setShowClearConfirm(false)
                      await onClearAllClips()
                    }}
                    className="h-6 text-[11px] px-2"
                  >
                    确认清空
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowClearConfirm(false)}
                    className="h-6 text-[11px] px-2"
                  >
                    取消
                  </Button>
                </div>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowClearConfirm(true)}
                  className="h-6 text-[11px] text-muted-foreground hover:text-destructive px-1.5"
                  aria-label="清空所有片段"
                >
                  <RotateCcw className="h-3 w-3 mr-1" />
                  清空所有片段
                </Button>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t">
          {/* 提交片段已选决策 */}
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="default"
              size="sm"
              disabled={clips.length === 0 || isSubmittingDecision}
              onClick={() => onDecision?.("clip_selected")}
              className={`gap-1.5 text-xs font-medium ${
                clips.length > 0
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                  : "border-dashed opacity-60 cursor-not-allowed"
              }`}
              aria-label={
                clips.length > 0
                  ? "提交审核决策：片段已选 (Clip selected)"
                  : "需至少添加 1 个片段方可提交片段已选"
              }
              data-testid="submit-clip-selected-btn"
            >
              {isSubmittingDecision ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Scissors className="h-3.5 w-3.5" />
              )}
              <span>提交片段已选 (Clip selected)</span>
              {clips.length > 0 && (
                <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                  {clips.length}
                </span>
              )}
            </Button>

            {clips.length === 0 && (
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <HelpCircle className="h-3 w-3" />
                <span>需至少 1 个有效片段</span>
              </span>
            )}
          </div>

          {/* 无需处理 (No action) - 保持独立且可逆 (Distinct & Reversible) */}
          <div className="flex items-center gap-2">
            {clips.length > 0 ? (
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isSubmittingDecision}
                  onClick={async () => {
                    // 若存在片段，标记 No Action 时先清空片段以满足后端约束并实现可逆切换
                    if (onClearAndRecordNoAction) {
                      await onClearAndRecordNoAction()
                    } else {
                      if (onClearAllClips) {
                        await onClearAllClips()
                      }
                      await onDecision?.("no_action")
                    }
                  }}
                  className="gap-1.5 text-xs border-blue-500/40 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/30"
                  aria-label="清空片段并标记为无需处理"
                  title="标记为无需处理要求清空片段，点击将清空片段并提交决策"
                  data-testid="clear-and-submit-no-action-btn"
                >
                  <RotateCcw className="h-3 w-3" />
                  <span>清空并标记无需处理 (No action)</span>
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isSubmittingDecision}
                onClick={() => onDecision?.("no_action")}
                className="gap-1.5 text-xs text-blue-600 border-blue-500/40 hover:bg-blue-50 dark:hover:bg-blue-950/30"
                aria-label="标记为无需处理 (No action)"
                data-testid="submit-no-action-btn"
              >
                {isSubmittingDecision ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CheckCheck className="h-3.5 w-3.5" />
                )}
                <span>无需处理 (No action)</span>
              </Button>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
export default ClipTimelineEditor
