import * as React from "react"
import { AppShell } from "@/components/layout/AppShell"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { FolderTree, Scissors, Archive, CheckCircle, Clock } from "lucide-react"

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
  const [loading, setLoading] = React.useState<boolean>(true)
  const [error, setError] = React.useState<string | null>(null)

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"

  React.useEffect(() => {
    fetch(`${apiBaseUrl}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`)
        return res.json()
      })
      .then((data: BackendHealth) => {
        setHealth(data)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [apiBaseUrl])

  return (
    <AppShell
      backendStatus={health?.status === "ok" ? "connected" : "checking"}
      apiBaseUrl={apiBaseUrl}
    >
      <div className="space-y-6">
        {/* 系统初始化状态卡片 */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>脚手架架构状态 (Scaffold Status)</CardTitle>
                <CardDescription>
                  Issue #1 基础脚手架已就绪，前后端服务配置、数据存储占位与组件规范已确立。
                </CardDescription>
              </div>
              <Badge variant="outline" className="border-primary/40 text-primary">
                v0.1.0-scaffold
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-lg border p-4 bg-muted/40">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">FastAPI 后端</span>
                  <Badge variant={health?.status === "ok" ? "success" : "secondary"}>
                    {loading ? "检测中..." : health?.status === "ok" ? "正常运行" : "就绪"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  健康检查接口: <code className="text-[11px] font-mono">/health</code> & <code className="text-[11px] font-mono">/api/health</code>
                </p>
                {error && (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                    本地未启动后端时前端提供无缝离线界面
                  </p>
                )}
              </div>

              <div className="rounded-lg border p-4 bg-muted/40">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">SQLite 数据库</span>
                  <Badge variant="outline">
                    {health?.database?.status || "占位就绪"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  数据引擎已配置，表结构与迁移由后续 Issue 实现
                </p>
              </div>

              <div className="rounded-lg border p-4 bg-muted/40">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">FFmpeg 服务</span>
                  <Badge variant="outline">
                    {health?.ffmpeg?.status || "接口占位"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  转码、截帧与裁剪调用接口已预留，不包含流媒体处理
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 目录挂载配置说明卡片 */}
        <Card>
          <CardHeader>
            <CardTitle>存储目录规范 (Storage Mounts)</CardTitle>
            <CardDescription>
              环境变量中定义的三个核心目录，用于隔离只读视频源、归档产物与隔离废弃文件。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col gap-2 p-4 rounded-lg border">
                <div className="flex items-center gap-2 font-medium text-sm">
                  <FolderTree className="h-4 w-4 text-blue-500" aria-hidden="true" />
                  <code>VIDEO_ROOTS</code>
                </div>
                <p className="text-xs text-muted-foreground">
                  待扫描与在线预览的源视频根目录列表（只读），支持多目录以分号分隔。
                </p>
              </div>

              <div className="flex flex-col gap-2 p-4 rounded-lg border">
                <div className="flex items-center gap-2 font-medium text-sm">
                  <Archive className="h-4 w-4 text-emerald-500" aria-hidden="true" />
                  <code>ARCHIVE_DIR</code>
                </div>
                <p className="text-xs text-muted-foreground">
                  裁剪后保留的精彩片段或整片归档存储目录（读写权限）。
                </p>
              </div>

              <div className="flex flex-col gap-2 p-4 rounded-lg border">
                <div className="flex items-center gap-2 font-medium text-sm">
                  <Scissors className="h-4 w-4 text-rose-500" aria-hidden="true" />
                  <code>DISCARDED_DIR</code>
                </div>
                <p className="text-xs text-muted-foreground">
                  初筛不合格视频的隔离移动目录（读写权限），避免误删源文件。
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 规划与边界提示 */}
        <Card className="border-dashed">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-amber-500" aria-hidden="true" />
              <CardTitle className="text-base">后续任务范围 (Next Steps Scope)</CardTitle>
            </div>
            <CardDescription>
              遵循 Issue #1 约束：当前脚手架严格不包含视频扫描、播放流媒体、裁剪处理、文件移动或认证逻辑。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-muted-foreground">
              <li className="flex items-center gap-2">
                <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                <span>Issue #1：基础脚手架、UI 外壳、配置规范与 CI 构建已就绪</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 ml-1 mr-1" />
                <span>后续 Issue：视频文件索引与目录递归扫描 (Video Scanning)</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 ml-1 mr-1" />
                <span>后续 Issue：HLS/MP4 时间轴平滑播放与预览 (Video Streaming)</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 ml-1 mr-1" />
                <span>后续 Issue：无损/重新编码裁剪处理任务队列 (Clip Processing)</span>
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}

export default App
