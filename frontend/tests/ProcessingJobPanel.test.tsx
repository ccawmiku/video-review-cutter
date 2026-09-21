import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ProcessingJobPanel } from "@/components/videos/ProcessingJobPanel"
import { ProcessingJob } from "@/types/video"

describe("ProcessingJobPanel", () => {
  const mockJobPending: ProcessingJob = {
    id: 101,
    video_id: 1,
    status: "pending",
    progress: 0.05,
    message: "排队等待处理中...",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }

  const mockJobRunning: ProcessingJob = {
    id: 102,
    video_id: 1,
    status: "running",
    progress: 0.45,
    message: "正在提取片段 1/2 并拼接...",
    strategy: "stream_copy_concat",
    created_at: new Date().toISOString(),
    started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }

  const mockJobCompleted: ProcessingJob = {
    id: 103,
    video_id: 1,
    status: "completed",
    progress: 1.0,
    message: "已完成视频原地替换与归档",
    strategy: "stream_copy_concat",
    output_path: "/media/videos/test.mp4",
    archive_path: "/media/archive/test_orig.mp4",
    created_at: new Date().toISOString(),
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }

  const mockJobFailed: ProcessingJob = {
    id: 104,
    video_id: 1,
    status: "failed",
    progress: 0.3,
    message: "FFmpeg 转码失败",
    error: "Invalid audio stream codec",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }

  it("renders start processing button when canStart is true", () => {
    const onStart = vi.fn().mockResolvedValue(undefined)
    render(
      <ProcessingJobPanel
        job={null}
        canStart={true}
        videoStatus="clip_selected"
        clipCount={2}
        onStartProcessing={onStart}
      />
    )

    const btn = screen.getByTestId("start-processing-btn")
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveTextContent("开始剪辑与替换 (Start Processing)")

    fireEvent.click(btn)
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it("disables start button when isStarting is true", () => {
    const onStart = vi.fn().mockResolvedValue(undefined)
    render(
      <ProcessingJobPanel
        job={null}
        canStart={true}
        isStarting={true}
        videoStatus="clip_selected"
        clipCount={2}
        onStartProcessing={onStart}
      />
    )

    const btn = screen.getByTestId("start-processing-btn")
    expect(btn).toBeDisabled()
    expect(btn).toHaveTextContent("正在启动任务...")
  })

  it("displays running job with progress percentage, stage message, and strategy", () => {
    const onStart = vi.fn()
    render(
      <ProcessingJobPanel
        job={mockJobRunning}
        canStart={false}
        videoStatus="clip_selected"
        clipCount={2}
        onStartProcessing={onStart}
      />
    )

    expect(screen.getByTestId("job-status-badge")).toHaveTextContent("剪辑处理中 (Processing)")
    expect(screen.getByTestId("job-progress-percent")).toHaveTextContent("45%")
    expect(screen.getByTestId("job-message")).toHaveTextContent("正在提取片段 1/2 并拼接...")
    expect(screen.getByText("无损流复制快速拼接")).toBeInTheDocument()

    // Active indicator is disabled to prevent duplicate starts
    expect(screen.getByTestId("processing-active-indicator")).toBeDisabled()
    expect(screen.queryByTestId("start-processing-btn")).not.toBeInTheDocument()
  })

  it("displays completed job with success notice and allow re-run", () => {
    const onStart = vi.fn()
    render(
      <ProcessingJobPanel
        job={mockJobCompleted}
        canStart={true}
        videoStatus="replaced"
        clipCount={2}
        onStartProcessing={onStart}
      />
    )

    expect(screen.getByTestId("job-status-badge")).toHaveTextContent("处理完成 (Completed)")
    expect(screen.getByTestId("job-progress-percent")).toHaveTextContent("100%")
    expect(screen.getByTestId("job-completed-notice")).toBeInTheDocument()

    const reRunBtn = screen.getByTestId("start-processing-btn")
    expect(reRunBtn).toBeInTheDocument()
    expect(reRunBtn).toHaveTextContent("重新执行剪辑")
  })

  it("displays failed job with error text and offers retry", () => {
    const onStart = vi.fn().mockResolvedValue(undefined)
    render(
      <ProcessingJobPanel
        job={mockJobFailed}
        canStart={true}
        videoStatus="clip_selected"
        clipCount={2}
        onStartProcessing={onStart}
      />
    )

    expect(screen.getByTestId("job-status-badge")).toHaveTextContent("处理失败 (Failed)")
    expect(screen.getByTestId("job-error")).toHaveTextContent("Invalid audio stream codec")

    const retryBtn = screen.getByTestId("start-processing-btn")
    expect(retryBtn).toHaveTextContent("重试剪辑处理")

    fireEvent.click(retryBtn)
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it("calls cancel handler when cancel button is clicked", () => {
    const onCancel = vi.fn().mockResolvedValue(undefined)
    render(
      <ProcessingJobPanel
        job={mockJobPending}
        canStart={false}
        videoStatus="clip_selected"
        clipCount={2}
        onStartProcessing={vi.fn()}
        onCancelProcessing={onCancel}
      />
    )

    const cancelBtn = screen.getByTestId("cancel-job-btn")
    expect(cancelBtn).toBeInTheDocument()
    fireEvent.click(cancelBtn)
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
