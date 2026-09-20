import { render, screen, waitFor, fireEvent, within, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import App from "../src/App"
import { VideoItem, VideoListResponse } from "../src/types/video"

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

describe("Video Review Queue & Task Mode (Issue #11)", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
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
            }),
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
        "http://localhost:8000/api/videos/101/preview"
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
        "http://localhost:8000/api/videos/106/preview"
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
})
