import { render, screen, fireEvent, waitFor, within } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ClipTimelineEditor } from "../src/components/videos/ClipTimelineEditor"
import { ClipSegment, VideoItem } from "../src/types/video"

const sampleVideo: VideoItem = {
  id: 101,
  video_id: 101,
  path: "/videos/sample.mp4",
  filename: "sample.mp4",
  size: 1024000,
  duration: 60.0,
  status: "unprocessed",
  created_at: "2026-09-20T10:00:00Z",
  updated_at: "2026-09-20T10:00:00Z",
  last_scanned_at: "2026-09-20T10:00:00Z",
}

const sampleClips: ClipSegment[] = [
  {
    id: 1,
    video_id: 101,
    start_seconds: 5.0,
    end_seconds: 15.0,
    order_index: 0,
    label: "精彩片头",
    note: "镜头快速切换",
  },
  {
    id: 2,
    video_id: 101,
    start_seconds: 20.0,
    end_seconds: 35.0,
    order_index: 1,
    label: "高潮对局",
    note: "双杀精彩镜头",
  },
]

describe("ClipTimelineEditor Component", () => {
  let onAddClip: ReturnType<typeof vi.fn>
  let onUpdateClip: ReturnType<typeof vi.fn>
  let onDeleteClip: ReturnType<typeof vi.fn>
  let onReorderClips: ReturnType<typeof vi.fn>
  let onDecision: ReturnType<typeof vi.fn>
  let onSeekVideo: ReturnType<typeof vi.fn>
  let onClearAllClips: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    onAddClip = vi.fn().mockResolvedValue(undefined)
    onUpdateClip = vi.fn().mockResolvedValue(undefined)
    onDeleteClip = vi.fn().mockResolvedValue(undefined)
    onReorderClips = vi.fn().mockResolvedValue(undefined)
    onDecision = vi.fn().mockResolvedValue(undefined)
    onSeekVideo = vi.fn()
    onClearAllClips = vi.fn().mockResolvedValue(undefined)
  })

  it("renders visual timeline and markers for multiple segments", () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
        onSeekVideo={onSeekVideo}
        onClearAllClips={onClearAllClips}
      />
    )

    // 验证标题和片段数量统计
    expect(screen.getByText("片段时间轴编辑器 (Clip Timeline)")).toBeInTheDocument()
    expect(screen.getByText("2 个片段")).toBeInTheDocument()

    // 验证可视化时间轴与标记
    expect(screen.getByTestId("clip-visual-timeline")).toBeInTheDocument()
    const marker1 = screen.getByTestId("timeline-marker-1")
    const marker2 = screen.getByTestId("timeline-marker-2")
    expect(marker1).toBeInTheDocument()
    expect(marker2).toBeInTheDocument()

    // 验证片段列表信息
    expect(screen.getByText("精彩片头")).toBeInTheDocument()
    expect(screen.getByText("高潮对局")).toBeInTheDocument()
    expect(screen.getByText("5s - 15s")).toBeInTheDocument()
    expect(screen.getByText("20s - 35s")).toBeInTheDocument()
  })

  it("provides keyboard-accessible numeric controls and steppers for adding segments", async () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
        onSeekVideo={onSeekVideo}
        onClearAllClips={onClearAllClips}
      />
    )

    // 点击添加片段展开表单
    const addBtn = screen.getByTestId("add-clip-button")
    fireEvent.click(addBtn)

    const form = screen.getByTestId("add-clip-form")
    expect(form).toBeInTheDocument()

    // 验证数字输入框具有标准 accessible 属性
    const startInput = screen.getByTestId("new-clip-start")
    const endInput = screen.getByTestId("new-clip-end")
    expect(startInput).toHaveAttribute("type", "number")
    expect(startInput).toHaveAttribute("step", "0.1")
    expect(endInput).toHaveAttribute("type", "number")

    // 测试步进微调按钮
    const plusStepBtn = within(form).getByRole("button", { name: "起始时间增加1秒" })
    fireEvent.click(plusStepBtn)

    // 验证标签与备注输入框已从 UI 中彻底移除
    expect(screen.queryByTestId("new-clip-label")).not.toBeInTheDocument()
    expect(screen.queryByTestId("new-clip-note")).not.toBeInTheDocument()

    // 保存片段
    const saveBtn = screen.getByTestId("save-new-clip-button")
    expect(saveBtn).not.toBeDisabled()
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(onAddClip).toHaveBeenCalledTimes(1)
      expect(onAddClip).toHaveBeenCalledWith(
        expect.objectContaining({
          label: null,
          note: null,
        })
      )
    })
  })

  it("validates bounds and blocks saving on invalid inputs: end <= start, negative, end > duration", async () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
      />
    )

    fireEvent.click(screen.getByTestId("add-clip-button"))
    const startInput = screen.getByTestId("new-clip-start")
    const endInput = screen.getByTestId("new-clip-end")
    const saveBtn = screen.getByTestId("save-new-clip-button")

    // 测试 1: 负数起始时间
    fireEvent.change(startInput, { target: { value: "-2" } })
    expect(screen.getByText(/起始时间不能为负数/i)).toBeInTheDocument()
    expect(saveBtn).toBeDisabled()

    // 测试 2: 结束时间 <= 起始时间
    fireEvent.change(startInput, { target: { value: "20" } })
    fireEvent.change(endInput, { target: { value: "15" } })
    expect(screen.getByText(/结束时间必须严格大于起始时间/i)).toBeInTheDocument()
    expect(saveBtn).toBeDisabled()

    // 测试 3: 结束时间超过视频时长 (60s)
    fireEvent.change(startInput, { target: { value: "50" } })
    fireEvent.change(endInput, { target: { value: "75" } })
    expect(screen.getByText(/不能超过视频总时长/i)).toBeInTheDocument()
    expect(saveBtn).toBeDisabled()

    // 测试 4: 恢复合法值 (10s 到 25s)
    fireEvent.change(startInput, { target: { value: "10" } })
    fireEvent.change(endInput, { target: { value: "25" } })
    expect(saveBtn).not.toBeDisabled()
  })

  it("edits an existing segment and saves changes via PATCH (without label/note inputs)", async () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
      />
    )

    // 点击片段 #1 的编辑按钮
    const editBtn = screen.getByTestId("edit-clip-button-1")
    fireEvent.click(editBtn)

    const editForm = screen.getByTestId("clip-edit-form-1")
    expect(editForm).toBeInTheDocument()

    const editStart = screen.getByTestId("edit-start-input-1")
    const editEnd = screen.getByTestId("edit-end-input-1")

    // 确认编辑界面中已移除标签和备注输入框
    expect(screen.queryByTestId("edit-label-input-1")).not.toBeInTheDocument()
    expect(screen.queryByTestId("edit-note-input-1")).not.toBeInTheDocument()

    fireEvent.change(editStart, { target: { value: "6.5" } })
    fireEvent.change(editEnd, { target: { value: "18.0" } })

    const saveEditBtn = screen.getByTestId("save-edit-button-1")
    fireEvent.click(saveEditBtn)

    await waitFor(() => {
      expect(onUpdateClip).toHaveBeenCalledWith(1, {
        start_seconds: 6.5,
        end_seconds: 18.0,
        label: "精彩片头",
        note: "镜头快速切换",
      })
    })
  })

  it("deletes a segment via onDeleteClip", async () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
      />
    )

    const deleteBtn = screen.getByTestId("delete-clip-1")
    fireEvent.click(deleteBtn)

    expect(onDeleteClip).toHaveBeenCalledWith(1)
  })

  it("reorders segments with Move Up and Move Down controls", async () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
      />
    )

    // 第一项的 Move Up 禁用
    const moveUpBtn1 = screen.getByTestId("move-up-clip-1")
    expect(moveUpBtn1).toBeDisabled()

    // 将第二项上移
    const moveUpBtn2 = screen.getByTestId("move-up-clip-2")
    expect(moveUpBtn2).not.toBeDisabled()
    fireEvent.click(moveUpBtn2)

    expect(onReorderClips).toHaveBeenCalledWith([sampleClips[1], sampleClips[0]])

    // 将第一项下移
    const moveDownBtn1 = screen.getByTestId("move-down-clip-1")
    fireEvent.click(moveDownBtn1)
    expect(onReorderClips).toHaveBeenCalledWith([sampleClips[1], sampleClips[0]])
  })

  it("enables 'clip_selected' submission only when at least 1 valid segment exists, and keeps 'no_action' distinct/reversible", async () => {
    // 场景 A: 0 个片段时
    const { rerender } = render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={[]}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
        onClearAllClips={onClearAllClips}
      />
    )

    const submitClipBtn = screen.getByTestId("submit-clip-selected-btn")
    expect(submitClipBtn).toBeDisabled()
    expect(screen.getByText(/需至少 1 个有效片段/i)).toBeInTheDocument()

    // 此时无需处理按钮可直接点击
    const noActionBtn = screen.getByTestId("submit-no-action-btn")
    expect(noActionBtn).not.toBeDisabled()
    fireEvent.click(noActionBtn)
    expect(onDecision).toHaveBeenCalledWith("no_action")

    // 场景 B: 存在片段时，提交片段已选可用；无需处理具备清空并提交的可逆路径
    rerender(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
        onClearAllClips={onClearAllClips}
      />
    )

    expect(submitClipBtn).not.toBeDisabled()
    fireEvent.click(submitClipBtn)
    expect(onDecision).toHaveBeenCalledWith("clip_selected")

    // 验证可逆清空并标记无需处理
    const clearNoActionBtn = screen.getByTestId("clear-and-submit-no-action-btn")
    expect(clearNoActionBtn).toBeInTheDocument()
    fireEvent.click(clearNoActionBtn)
    await waitFor(() => {
      expect(onClearAllClips).toHaveBeenCalledTimes(1)
      expect(onDecision).toHaveBeenCalledWith("no_action")
    })
  })

  it("triggers video seek when clicking timeline markers or seek button", () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
        onSeekVideo={onSeekVideo}
      />
    )

    // 点击时间轴标记
    const marker = screen.getByTestId("timeline-marker-1")
    fireEvent.click(marker)
    expect(onSeekVideo).toHaveBeenCalledWith(5.0)

    // 点击片段旁的播放定位按钮
    const playBtn = screen.getByRole("button", { name: /定位到片段 #2 起点/i })
    fireEvent.click(playBtn)
    expect(onSeekVideo).toHaveBeenCalledWith(20.0)
  })

  it("allows selecting a segment and deleting only the selected segment via the header button without deleting all segments", async () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
        onSeekVideo={onSeekVideo}
        onClearAllClips={onClearAllClips}
      />
    )

    // 初始状态下未选中任何片段，不显示“删除选中片段”按钮
    expect(screen.queryByTestId("delete-selected-clip-btn")).not.toBeInTheDocument()

    // 点击列表中的片段 #1 进行选中
    const clipItem1 = screen.getByTestId("clip-segment-item-1")
    fireEvent.click(clipItem1)

    // 验证高亮选中状态及头部出现的“删除选中片段”按钮
    expect(within(clipItem1).getByText("已选中")).toBeInTheDocument()
    const deleteSelectedBtn = screen.getByTestId("delete-selected-clip-btn")
    expect(deleteSelectedBtn).toBeInTheDocument()

    // 点击删除选中片段
    fireEvent.click(deleteSelectedBtn)

    // 验证仅调用 onDeleteClip(1)，绝不调用 onClearAllClips
    expect(onDeleteClip).toHaveBeenCalledTimes(1)
    expect(onDeleteClip).toHaveBeenCalledWith(1)
    expect(onClearAllClips).not.toHaveBeenCalled()
  })

  it("allows selecting a segment via timeline marker and deleting it via row delete button without deleting other segments", async () => {
    render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
        onDecision={onDecision}
        onSeekVideo={onSeekVideo}
        onClearAllClips={onClearAllClips}
      />
    )

    // 点击时间轴片段 #2 的 marker 进行选中与定位
    const marker2 = screen.getByTestId("timeline-marker-2")
    fireEvent.click(marker2)
    expect(onSeekVideo).toHaveBeenCalledWith(20.0)

    const clipItem2 = screen.getByTestId("clip-segment-item-2")
    expect(within(clipItem2).getByText("已选中")).toBeInTheDocument()

    // 点击片段 #2 单独的删除按钮
    const deleteRowBtn = screen.getByTestId("delete-clip-2")
    fireEvent.click(deleteRowBtn)

    // 验证只删除了片段 #2
    expect(onDeleteClip).toHaveBeenCalledTimes(1)
    expect(onDeleteClip).toHaveBeenCalledWith(2)
    expect(onClearAllClips).not.toHaveBeenCalled()
  })

  it("renders clip loading state when isLoadingClips is true and switches to clips list when done", () => {
    const { rerender } = render(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={[]}
        isLoadingClips={true}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
      />
    )

    expect(screen.getByText("加载片段列表中...")).toBeInTheDocument()
    expect(screen.queryByTestId("no-clips-placeholder")).not.toBeInTheDocument()

    // 加载完成后切换为正常状态
    rerender(
      <ClipTimelineEditor
        video={sampleVideo}
        clips={sampleClips}
        isLoadingClips={false}
        onAddClip={onAddClip}
        onUpdateClip={onUpdateClip}
        onDeleteClip={onDeleteClip}
        onReorderClips={onReorderClips}
      />
    )

    expect(screen.queryByText("加载片段列表中...")).not.toBeInTheDocument()
    expect(screen.getByTestId("clip-segment-item-1")).toBeInTheDocument()
    expect(screen.getByTestId("clip-segment-item-2")).toBeInTheDocument()
  })
})
