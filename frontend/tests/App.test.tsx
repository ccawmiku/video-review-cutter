import { render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import App from "../src/App"

describe("App & AppShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "ok",
          app: "video-review-cutter-backend",
          version: "0.1.0",
          environment: "development",
          database: { status: "connected", type: "sqlite" },
          ffmpeg: { available: true, status: "placeholder_ready" },
          storage: {
            video_roots_count: 1,
            archive_configured: true,
            discarded_configured: true,
          },
        }),
      })
    )
  })

  it("renders accessible landmark roles: banner, main, and contentinfo", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole("banner")).toBeInTheDocument()
      expect(screen.getByRole("main")).toBeInTheDocument()
      expect(screen.getByRole("contentinfo")).toBeInTheDocument()
    })
  })

  it("renders accessible skip link targeting #main-content", async () => {
    render(<App />)

    await waitFor(() => {
      const skipLink = screen.getByText(/跳至主要内容/i)
      expect(skipLink).toBeInTheDocument()
      expect(skipLink).toHaveAttribute("href", "#main-content")
    })
  })

  it("renders application title and scaffold cards", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByText("视频在线预览裁剪")).toBeInTheDocument()
      expect(screen.getByText(/脚手架架构状态/i)).toBeInTheDocument()
    })
  })

  it("documents required directory mounts in UI", async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByText("VIDEO_ROOTS")).toBeInTheDocument()
      expect(screen.getByText("ARCHIVE_DIR")).toBeInTheDocument()
      expect(screen.getByText("DISCARDED_DIR")).toBeInTheDocument()
    })
  })
})
