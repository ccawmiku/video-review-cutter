import * as React from "react"
import { Film, HardDrive, CheckCircle2, AlertCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"

interface AppShellProps {
  children: React.ReactNode
  backendStatus?: "connected" | "disconnected" | "checking"
  apiBaseUrl?: string
}

export function AppShell({
  children,
  backendStatus = "connected",
  apiBaseUrl = "http://localhost:8000",
}: AppShellProps) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      {/* 键盘无障碍跳过导航链接 */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 z-50 px-4 py-2 bg-primary text-primary-foreground rounded-md shadow-md focus:outline-none"
      >
        跳至主要内容 (Skip to content)
      </a>

      {/* 顶部导航栏 */}
      <header
        role="banner"
        className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60"
      >
        <div className="container mx-auto flex h-16 items-center justify-between px-4 sm:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Film className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">视频在线预览裁剪</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">
                Video Review & Cutter · 初始架构脚手架
              </p>
            </div>
          </div>

          {/* 状态指示器与导航 */}
          <nav aria-label="系统与服务状态" className="flex items-center gap-3">
            <div className="hidden md:flex items-center text-xs text-muted-foreground gap-1.5 mr-2">
              <HardDrive className="h-3.5 w-3.5" aria-hidden="true" />
              <span>API: <code className="bg-muted px-1.5 py-0.5 rounded text-[11px]">{apiBaseUrl}</code></span>
            </div>

            {backendStatus === "connected" ? (
              <Badge variant="success" className="flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                <span>后端已就绪</span>
              </Badge>
            ) : (
              <Badge variant="secondary" className="flex items-center gap-1">
                <AlertCircle className="h-3 w-3" aria-hidden="true" />
                <span>连接检查中</span>
              </Badge>
            )}
          </nav>
        </div>
      </header>

      {/* 主要内容区域 */}
      <main id="main-content" role="main" tabIndex={-1} className="flex-1 container mx-auto px-4 sm:px-8 py-8 focus:outline-none">
        {children}
      </main>

      {/* 页脚 */}
      <footer role="contentinfo" className="border-t bg-background py-6 text-center text-xs text-muted-foreground">
        <div className="container mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>视频在线预览裁剪 (Video Review & Cutter) · Issue #1 Scaffold</span>
          <span>FastAPI + SQLite + FFmpeg + React + Tailwind CSS</span>
        </div>
      </footer>
    </div>
  )
}
