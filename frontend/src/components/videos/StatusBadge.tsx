import * as React from "react"
import { Badge } from "@/components/ui/badge"
import { VideoStatus } from "@/types/video"
import { Circle, CheckCheck, Scissors, Trash2, ArrowLeftRight } from "lucide-react"

interface StatusBadgeProps {
  status: VideoStatus
  className?: string
}

const statusConfig: Record<
  VideoStatus,
  {
    label: string
    variant: "default" | "secondary" | "destructive" | "outline" | "success"
    colorClass: string
    icon: React.ComponentType<{ className?: string }>
  }
> = {
  unprocessed: {
    label: "未处理",
    variant: "outline",
    colorClass: "border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 bg-slate-50/50 dark:bg-slate-900/50",
    icon: Circle,
  },
  no_action: {
    label: "无需处理",
    variant: "secondary",
    colorClass: "bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30",
    icon: CheckCheck,
  },
  clip_selected: {
    label: "片段已选",
    variant: "success",
    colorClass: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    icon: Scissors,
  },
  discarded: {
    label: "已废弃",
    variant: "destructive",
    colorClass: "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30",
    icon: Trash2,
  },
  replaced: {
    label: "已替换",
    variant: "outline",
    colorClass: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
    icon: ArrowLeftRight,
  },
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status] ?? statusConfig.unprocessed
  const Icon = config.icon

  return (
    <Badge
      variant={config.variant}
      className={`inline-flex items-center gap-1.5 font-medium ${config.colorClass} ${className || ""}`}
      role="status"
      aria-label={`状态: ${config.label}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      <span>{config.label}</span>
    </Badge>
  )
}
