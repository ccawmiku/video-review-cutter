import { render, screen, waitFor, fireEvent, within, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import App from "../src/App"
import { ClipSegment, ProcessingJob, VideoItem, VideoListResponse } from "../src/types/video"

const mockVideos: VideoItem[] = [
  {
    id: 101,
    video_id: 101,
    path: "/videos/action_movie_part1.mp4",
    filename: "action_movie_part1.mp4",
    size: 2147483648,
    duration: 3600.0,
    status: "unprocessed",
    width: 1920,
    height: 1080,
    codec: "h264",
    fps: 60.0,
    bit_rate: 5000000,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
    last_scanned_at: "2026-09-20T10:00:00Z",
    clips: [],
  },
  {
    id: 102,
    video_id: 102,
    path: "/videos/interview_clip.mp4",
    filename: "interview_clip.mp4",
    size: 524288000,
    duration: 1800.0,
    status: "no_action",
    width: 1280,
    height: 720,
    codec: "h265",
    fps: 30.0,
    bit_rate: 2500000,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
    last_scanned_at: "2026-09-20T10:00:00Z",
    clips: [],
  },
  {
    id: 103,
    video_id: 103,
    path: "/videos/tutorial_intro.mp4",
    filename: "tutorial_intro.mp4",
    size: 1073741824,
    duration: 900.0,
    status: "clip_selected",
    width: 3840,
    height: 2160,
    codec: "vp9",
    fps: 30.0,
    bit_rate: 8000000,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
    last_scanned_at: "2026-09-20T10:00:00Z",
    clips: [
      {
        id: 1,
        video_id: 103,
        start_seconds: 10,
        end_seconds: 25,
        duration_seconds: 15,
        order_index: 0,
      },
    ],
  },
  {
    id: 104,
    video_id: 104,
    path: "/videos/discarded_bad_audio.mp4",
    filename: "discarded_bad_audio.mp4",
    size: 300000000,
    duration: 600.0,
    status: "discarded",
    width: 1920,
    height: 1080,
    codec: "h264",
    fps: 24.0,
    bit_rate: 2000000,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
    last_scanned_at: "2026-09-20T10:00:00Z",
    clips: [],
  },
  {
    id: 105,
    video_id: 105,
    path: "/videos/replaced_version.mp4",
    filename: "replaced_version.mp4",
    size: 150000000,
    duration: 300.0,
    status: "replaced",
    width: 1920,
    height: 1080,
    codec: "h264",
    fps: 30.0,
    bit_rate: 1500000,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
    last_scanned_at: "2026-09-20T10:00:00Z",
    clips: [],
  },
  {
    id: 106,
    video_id: 106,
    path: "/videos/another_unprocessed.mp4",
    filename: "another_unprocessed.mp4",
    size: 80000000,
    duration: 120.0,
    status: "unprocessed",
    width: 1920,
    height: 1080,
    codec: "h264",
    fps: 30.0,
    bit_rate: 1000000,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
    last_scanned_at: "2026-09-20T10:00:00Z",
    clips: [],
  },
]

let dynamicClips: Record<number, ClipSegment[]> = {}

describe("Video Review Queue & Task Mode (Issue #11)", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    dynamicClips = {
      101: [],
      102: [],
      103: [
        {
          id: 1,
          video_id: 103,
          start_seconds: 10,
          end_seconds: 25,
          duration_seconds: 15,
          order_index: 0,
          label: "精彩导语",
        },
      ],
      104: [],
      105: [],
      106: [],
    }

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url.includes("/health")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              status: "ok",
              app: "video-review-cutter-backend",
              version: "0.1.0",
              environment: "development",
            }),
          })
        }

        // 匹配 GET /api/videos/{id}/clips
        const clipsMatch = url.match(/\/api\/videos\/(\d+)\/clips(?:\/(\d+))?/)
        if (clipsMatch) {
          const videoId = Number(clipsMatch[1])
          const clipId = clipsMatch[2] ? Number(clipsMatch[2]) : null
          const method = init?.method || "GET"

          if (method === "GET") {
            return Promise.resolve({
              ok: true,
              json: async () => dynamicClips[videoId] || [],
            })
          }

          if (method === "POST") {
            const body = JSON.parse(init?.body as string)
            const newClip: ClipSegment = {
              id: Date.now(),
              video_id: videoId,
              start_seconds: body.start_seconds,
              end_seconds: body.end_seconds,
              label: body.label || null,
              note: body.note || null,
              order_index: body.order_index ?? (dynamicClips[videoId]?.length || 0),
            }
            dynamicClips[videoId] = [...(dynamicClips[videoId] || []), newClip]
            return Promise.resolve({
              ok: true,
              status: 201,
              json: async () => newClip,
            })
          }

          if (method === "PATCH" && clipId) {
            const body = JSON.parse(init?.body as string)
            const list = dynamicClips[videoId] || []
            dynamicClips[videoId] = list.map((c) => (c.id === clipId ? { ...c, ...body } : c))
            const updated = dynamicClips[videoId].find((c) => c.id === clipId)
            return Promise.resolve({
              ok: true,
              json: async () => updated,
            })
          }

          if (method === "DELETE" && clipId) {
            const list = dynamicClips[videoId] || []
            dynamicClips[videoId] = list.filter((c) => c.id !== clipId)
            return Promise.resolve({
              ok: true,
              status: 204,
              json: async () => ({}),
            })
          }
        }

        if (url.includes("/api/videos?") || url.endsWith("/api/videos")) {
          const parsed = new URL(url, "http://localhost:8000")
          const status = parsed.searchParams.get("status")

          let filtered = [...mockVideos]
          if (status && status !== "all") {
            filtered = filtered.filter((v) => v.status === status)
          }

          const response: VideoListResponse = {
            items: filtered,
            total: filtered.length,
            page: Number(parsed.searchParams.get("page") || 1),
            page_size: Number(parsed.searchParams.get("page_size") || 20),
            total_pages: 1,
          }

          return Promise.resolve({
            ok: true,
            json: async () => response,
          })
        }

        if (url.includes("/decision") && init?.method === "POST") {
          const body = JSON.parse(init.body as string)
          const videoId = Number(url.split("/api/videos/")[1].split("/decision")[0])
          const video = mockVideos.find((v) => v.id === videoId) || mockVideos[0]
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...video,
              status: body.decision,
              decision: body.decision,
              clips: dynamicClips[videoId] || [],
            }),
          })
        }

        if (url.includes("/process") && init?.method === "POST") {
          const videoId = Number(url.split("/api/videos/")[1].split("/process")[0])
          const job: ProcessingJob = {
            id: 201,
            video_id: videoId,
            status: "running",
            progress: 0.5,
            message: "正在提取片段并拼接...",
            strategy: "stream_copy_concat",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }
          return Promise.resolve({
            ok: true,
            json: async () => job,
          })
        }

        if (url.includes("/jobs/latest")) {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: async () => ({ detail: "Not found" }),
          })
        }

        return Promise.resolve({
          ok: true,
          json: async () => ({}),
        })
      })
    )
  })

  it("renders accessible landmark roles: banner, main, contentinfo, and skip link", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole("banner")).toBeInTheDocument()
      expect(screen.getByRole("main")).toBeInTheDocument()
      expect(screen.getByRole("contentinfo")).toBeInTheDocument()
      const skipLink = screen.getByText(/跳至主要内容/i)
      expect(skipLink).toBeInTheDocument()
      expect(skipLink).toHaveAttribute("href", "#main-content")
    })
  })

  it("fetches and displays videos sorted by duration descending with filename, duration, metadata and 5 status badges", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)
      expect(screen.getAllByText("interview_clip.mp4").length).toBeGreaterThan(0)
      expect(screen.getAllByText("tutorial_intro.mp4").length).toBeGreaterThan(0)
      expect(screen.getAllByText("discarded_bad_audio.mp4").length).toBeGreaterThan(0)
      expect(screen.getAllByText("replaced_version.mp4").length).toBeGreaterThan(0)
    })

    // 验证格式化后的时长
    expect(screen.getAllByText("1:00:00").length).toBeGreaterThan(0) // 3600秒
    expect(screen.getAllByText("30:00").length).toBeGreaterThan(0) // 1800秒
    expect(screen.getAllByText("15:00").length).toBeGreaterThan(0) // 900秒

    // 验证五种不同的状态徽章
    expect(screen.getAllByText("未处理").length).toBeGreaterThan(0)
    expect(screen.getAllByText("无需处理").length).toBeGreaterThan(0)
    expect(screen.getAllByText("片段已选").length).toBeGreaterThan(0)
    expect(screen.getAllByText("已废弃").length).toBeGreaterThan(0)
    expect(screen.getAllByText("已替换").length).toBeGreaterThan(0)

    // 验证按时长降序标识
    expect(screen.getByText(/按时长降序/i)).toBeInTheDocument()
  })

  it("renders an HTML5 video preview player using GET /api/videos/{id}/preview", async () => {
    render(<App />)

    await waitFor(() => {
      const videoPlayer = screen.getByTestId("video-preview-player")
      expect(videoPlayer).toBeInTheDocument()
      expect(videoPlayer).toHaveAttribute(
        "src",
        "/api/videos/101/preview"
      )
      expect(videoPlayer).toHaveAttribute("controls")
    })
  })

  it("activates task mode, auto-focuses first unprocessed video, and shows decision actions", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)
    })

    // 点击进入任务模式
    const taskModeBtn = screen.getByRole("button", { name: /任务模式/i })
    fireEvent.click(taskModeBtn)

    // 验证任务模式面板
    await waitFor(() => {
      const region = screen.getByRole("region", { name: /任务模式决策面板/i })
      expect(region).toBeInTheDocument()
      expect(within(region).getByRole("button", { name: /标记为无需处理/i })).toBeInTheDocument()
      expect(within(region).getByRole("button", { name: /片段已选/i })).toBeInTheDocument()
      expect(within(region).getByRole("button", { name: /跳过/i })).toBeInTheDocument()
    })
  })

  it("executes 'No action' decision, calls API, updates status and advances to next unprocessed video", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)
    })

    // 进入任务模式
    const taskModeBtn = screen.getByRole("button", { name: /任务模式/i })
    fireEvent.click(taskModeBtn)

    // 点击 "无需处理 (No action)"
    const region = screen.getByRole("region", { name: /任务模式决策面板/i })
    const noActionBtn = within(region).getByRole("button", { name: /标记为无需处理/i })
    fireEvent.click(noActionBtn)

    // 验证成功反馈与自动推进到下一个未处理视频 (id: 106 another_unprocessed.mp4)
    await waitFor(() => {
      expect(screen.getByText(/成功记录为：无需处理/i)).toBeInTheDocument()
      const videoPlayer = screen.getByTestId("video-preview-player")
      expect(videoPlayer).toHaveAttribute(
        "src",
        "/api/videos/106/preview"
      )
    })
  })

  it("provides clear disabled state and explanation for 'Clip selected' when video has 0 clips", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)
    })

    // 进入任务模式 (当前未处理视频 action_movie_part1.mp4 的 clips 为 0)
    const taskModeBtn = screen.getByRole("button", { name: /任务模式/i })
    fireEvent.click(taskModeBtn)

    await waitFor(() => {
      const region = screen.getByRole("region", { name: /任务模式决策面板/i })
      const clipSelectedBtn = within(region).getByRole("button", {
        name: /需先通过时间轴编辑器选定片段/i,
      })
      expect(clipSelectedBtn).toBeDisabled()
      expect(screen.getByText(/需至少 1 个片段（待时间轴 UI 支持）/i)).toBeInTheDocument()
    })
  })

  it("allows switching status filter tabs and refetches filtered data", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)
    })

    // 点击筛选选项 "已废弃"
    const discardedTab = screen.getByRole("tab", { name: "已废弃" })
    fireEvent.click(discardedTab)

    await waitFor(() => {
      expect(screen.getAllByText("discarded_bad_audio.mp4").length).toBeGreaterThan(0)
      expect(screen.queryByText("action_movie_part1.mp4")).not.toBeInTheDocument()
    })
  })

  it("handles loading and error states gracefully with retry action", async () => {
    // 模拟接口失败
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/videos")) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: async () => ({ detail: "Database connection failed" }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "ok" }),
        })
      })
    )

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText(/加载视频队列出错/i)).toBeInTheDocument()
      expect(screen.getByText(/Database connection failed/i)).toBeInTheDocument()
    })

    const retryBtn = screen.getByRole("button", { name: /重新重试/i })
    expect(retryBtn).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(retryBtn)
    })
  })

  it("renders helpful empty state when no videos match query", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/videos")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              items: [],
              total: 0,
              page: 1,
              page_size: 20,
              total_pages: 0,
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "ok" }),
        })
      })
    )

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText(/暂无符合条件的视频/i)).toBeInTheDocument()
    })
  })

  it("integrates clip timeline editor with review queue: renders visual timeline and supports adding/editing clips", async () => {
    render(<App />)

    // 默认选中第一个视频 (101: action_movie_part1.mp4)
    await waitFor(() => {
      expect(screen.getByTestId("clip-timeline-editor")).toBeInTheDocument()
      expect(screen.getByTestId("clip-visual-timeline")).toBeInTheDocument()
      expect(screen.getByText(/暂无裁剪片段/i)).toBeInTheDocument()
    })

    // 点击添加片段
    const addBtn = screen.getByTestId("add-clip-button")
    fireEvent.click(addBtn)

    const form = screen.getByTestId("add-clip-form")
    expect(form).toBeInTheDocument()

    // 填入时间（标签与备注输入框已移除）
    const startInput = screen.getByTestId("new-clip-start")
    const endInput = screen.getByTestId("new-clip-end")
    expect(screen.queryByTestId("new-clip-label")).not.toBeInTheDocument()
    expect(screen.queryByTestId("new-clip-note")).not.toBeInTheDocument()

    fireEvent.change(startInput, { target: { value: "5.0" } })
    fireEvent.change(endInput, { target: { value: "20.0" } })

    const saveBtn = screen.getByTestId("save-new-clip-button")
    fireEvent.click(saveBtn)

    // 验证片段已保存并显示在列表和时间轴上
    await waitFor(() => {
      expect(screen.getByText("5s - 20s")).toBeInTheDocument()
      expect(screen.getByText(/1 个片段/i)).toBeInTheDocument()
    })

    // 验证提交片段已选决策按钮可用并点击提交
    const submitClipBtn = screen.getByTestId("submit-clip-selected-btn")
    expect(submitClipBtn).not.toBeDisabled()
    fireEvent.click(submitClipBtn)

    await waitFor(() => {
      expect(screen.getByText(/成功记录为：片段已选/i)).toBeInTheDocument()
    })
  })

  it("supports reversible review decision: switching between no_action and clip_selected", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId("clip-timeline-editor")).toBeInTheDocument()
    })

    // 当前视频 101 无片段，直接点击无需处理 (No action)
    const noActionBtn = screen.getByTestId("submit-no-action-btn")
    fireEvent.click(noActionBtn)

    await waitFor(() => {
      expect(screen.getByText(/成功记录为：无需处理/i)).toBeInTheDocument()
    })

    // 可逆切换：添加 1 个片段以反转为片段已选
    fireEvent.click(screen.getByTestId("add-clip-button"))
    fireEvent.change(screen.getByTestId("new-clip-start"), { target: { value: "10" } })
    fireEvent.change(screen.getByTestId("new-clip-end"), { target: { value: "30" } })
    fireEvent.click(screen.getByTestId("save-new-clip-button"))

    await waitFor(() => {
      expect(screen.getByText("10s - 30s")).toBeInTheDocument()
    })

    // 提交片段已选以反转之前 无需处理 的决策
    const submitClipBtn = screen.getByTestId("submit-clip-selected-btn")
    expect(submitClipBtn).not.toBeDisabled()
    fireEvent.click(submitClipBtn)

    await waitFor(() => {
      expect(screen.getByText(/成功记录为：片段已选/i)).toBeInTheDocument()
    })

    // 再次可逆切换：清空片段并恢复为无需处理
    const clearNoActionBtn = screen.getByTestId("clear-and-submit-no-action-btn")
    fireEvent.click(clearNoActionBtn)

    await waitFor(() => {
      expect(screen.getByText(/成功记录为：无需处理/i)).toBeInTheDocument()
    })
  })

  it("keeps existing catalog visible and shows refreshing indicator when refreshing videos in background without replacing with empty state", async () => {
    render(<App />)

    // 等待初始加载完成并展示视频列表
    await waitFor(() => {
      expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)
    })

    // 点击刷新按钮
    const refreshBtn = screen.getByTestId("refresh-videos-button")
    fireEvent.click(refreshBtn)

    // 验证在刷新进行中及之后，现有视频目录始终保持可见，且绝不会被空状态替换
    expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)
    expect(screen.queryByTestId("initial-loading-state")).not.toBeInTheDocument()
    expect(screen.queryByText("暂无符合条件的视频")).not.toBeInTheDocument()

    // 等待刷新完成
    await waitFor(() => {
      expect(screen.getByText("刷新")).toBeInTheDocument()
    })
  })

  it("finishes loading clips without getting stuck on 加载片段列表中 when switching selected videos", async () => {
    render(<App />)

    // 初始视频 101 加载完成，确认加载状态消失且显示暂无片段
    await waitFor(() => {
      expect(screen.queryByText("加载片段列表中...")).not.toBeInTheDocument()
      expect(screen.getByText(/暂无裁剪片段/i)).toBeInTheDocument()
    })

    // 切换选中视频到 103 (tutorial_intro.mp4，包含 1 个片段)
    const video103Btn = screen.getByRole("button", {
      name: /选择视频 tutorial_intro\.mp4/i,
    })
    fireEvent.click(video103Btn)

    // 验证片段列表加载完成，展示对应片段，绝不处于“加载片段列表中...”的永久卡死状态
    await waitFor(() => {
      expect(screen.queryByText("加载片段列表中...")).not.toBeInTheDocument()
      expect(screen.getByText("10s - 25s")).toBeInTheDocument()
    })
  })

  it("allows selecting and deleting a single saved clip without deleting other clips", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId("clip-timeline-editor")).toBeInTheDocument()
    })

    // 为视频 101 添加第 1 个片段 (5s - 15s)
    fireEvent.click(screen.getByTestId("add-clip-button"))
    fireEvent.change(screen.getByTestId("new-clip-start"), { target: { value: "5.0" } })
    fireEvent.change(screen.getByTestId("new-clip-end"), { target: { value: "15.0" } })
    fireEvent.click(screen.getByTestId("save-new-clip-button"))

    await waitFor(() => {
      expect(screen.getByText("5s - 15s")).toBeInTheDocument()
      expect(screen.getByText("1 个片段")).toBeInTheDocument()
    })

    // 为视频 101 添加第 2 个片段 (20s - 30s)
    fireEvent.click(screen.getByTestId("add-clip-button"))
    fireEvent.change(screen.getByTestId("new-clip-start"), { target: { value: "20.0" } })
    fireEvent.change(screen.getByTestId("new-clip-end"), { target: { value: "30.0" } })
    fireEvent.click(screen.getByTestId("save-new-clip-button"))

    await waitFor(() => {
      expect(screen.getByText("20s - 30s")).toBeInTheDocument()
      expect(screen.getByText("2 个片段")).toBeInTheDocument()
    })

    // 单独删除第 1 个片段
    const deleteBtn1 = screen.getByRole("button", { name: "删除片段 #1" })
    fireEvent.click(deleteBtn1)

    // 验证成功反馈、第 1 个片段被移除，而第 2 个片段 (20s - 30s) 依然完好保留，未删除全部片段
    await waitFor(() => {
      expect(screen.getByText("已成功删除片段")).toBeInTheDocument()
      expect(screen.queryByText("5s - 15s")).not.toBeInTheDocument()
      expect(screen.getByText("20s - 30s")).toBeInTheDocument()
      expect(screen.getByText("1 个片段")).toBeInTheDocument()
    })
  })

  it("makes review queue collapsible like a sidebar with accessible toggle, expanding preview/timeline to main area while preserving selected video state", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "折叠视频审核队列" })).toBeInTheDocument()
      expect(screen.getByTestId("video-preview-player")).toHaveAttribute("src", "/api/videos/101/preview")
    })

    const sidebar = document.getElementById("review-queue-sidebar")
    const mainArea = screen.getByTestId("main-content-area")
    expect(sidebar).not.toHaveClass("hidden")
    expect(mainArea).toHaveClass("lg:col-span-7")

    // 点击收起队列折叠侧边栏
    const collapseBtn = screen.getByRole("button", { name: "折叠视频审核队列" })
    expect(collapseBtn).toHaveAttribute("aria-expanded", "true")
    fireEvent.click(collapseBtn)

    // 验证侧边栏已隐藏，主内容区域占据全部宽度 (lg:col-span-12)
    expect(sidebar).toHaveClass("hidden")
    expect(mainArea).toHaveClass("lg:col-span-12")

    // 验证选中的视频状态保持完好
    const player = screen.getByTestId("video-preview-player")
    expect(player).toHaveAttribute("src", "/api/videos/101/preview")
    expect(screen.getAllByText("action_movie_part1.mp4").length).toBeGreaterThan(0)

    // 验证展开按钮具有可访问属性并可重新展开侧边栏
    const expandBtn = screen.getByRole("button", { name: "展开视频审核队列" })
    expect(expandBtn).toHaveAttribute("aria-expanded", "false")
    fireEvent.click(expandBtn)

    // 验证侧边栏恢复可见，主内容区恢复标准布局
    expect(sidebar).not.toHaveClass("hidden")
    expect(mainArea).toHaveClass("lg:col-span-7")
    expect(player).toHaveAttribute("src", "/api/videos/101/preview")
  })

  it("seeks video and pauses player when focusing or editing clip start/end timestamps or using nudge buttons", async () => {
    const pauseSpy = vi.spyOn(window.HTMLMediaElement.prototype, "pause")

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId("clip-timeline-editor")).toBeInTheDocument()
      expect(screen.getByTestId("video-preview-player")).toBeInTheDocument()
    })

    const player = screen.getByTestId("video-preview-player") as HTMLVideoElement

    // 打开添加片段表单
    fireEvent.click(screen.getByTestId("add-clip-button"))
    const startInput = screen.getByTestId("new-clip-start")
    const endInput = screen.getByTestId("new-clip-end")

    // 1. 获得焦点触发 seek 和 pause
    pauseSpy.mockClear()
    fireEvent.focus(startInput)
    expect(player.currentTime).toBe(0)
    expect(pauseSpy).toHaveBeenCalled()

    // 2. 编辑起始时间触发 seek 和 pause
    pauseSpy.mockClear()
    fireEvent.change(startInput, { target: { value: "15.5" } })
    expect(player.currentTime).toBe(15.5)
    expect(pauseSpy).toHaveBeenCalled()

    // 3. 获得结束时间焦点并编辑
    pauseSpy.mockClear()
    fireEvent.focus(endInput)
    expect(player.currentTime).toBe(10)
    expect(pauseSpy).toHaveBeenCalled()

    pauseSpy.mockClear()
    fireEvent.change(endInput, { target: { value: "40.0" } })
    expect(player.currentTime).toBe(40.0)
    expect(pauseSpy).toHaveBeenCalled()

    // 4. 点击 +/-30s 微调按钮触发 seek 和 pause
    pauseSpy.mockClear()
    const startPlus30 = screen.getByTestId("new-clip-start-plus-30")
    fireEvent.click(startPlus30) // 15.5 + 30 = 45.5
    expect(player.currentTime).toBe(45.5)
    expect(pauseSpy).toHaveBeenCalled()
  })

  it("provides explicit start processing button in clip_selected status, triggers POST /process, and shows job progress", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId("clip-timeline-editor")).toBeInTheDocument()
    })

    // 选择第 3 个视频 (id: 103, status: "clip_selected")
    fireEvent.click(screen.getByText("tutorial_intro.mp4"))

    await waitFor(() => {
      expect(screen.getByTestId("start-processing-btn")).toBeInTheDocument()
      expect(screen.getByTestId("start-processing-btn")).toHaveTextContent("开始剪辑与替换 (Start Processing)")
    })

    // 点击开始剪辑
    fireEvent.click(screen.getByTestId("start-processing-btn"))

    // 验证展示任务进度
    await waitFor(() => {
      expect(screen.getByTestId("job-status-badge")).toHaveTextContent("剪辑处理中 (Processing)")
      expect(screen.getByTestId("job-progress-percent")).toHaveTextContent("50%")
      expect(screen.getByTestId("job-message")).toHaveTextContent("正在提取片段并拼接...")
      expect(screen.getByText("无损流复制快速拼接")).toBeInTheDocument()
      expect(screen.getByTestId("processing-active-indicator")).toBeInTheDocument()
    })
  })
})

