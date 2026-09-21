/**
 * Video Catalog and Review Workflow Types
 */

export type VideoStatus =
  | "unprocessed"
  | "no_action"
  | "clip_selected"
  | "discarded"
  | "replaced"

export interface ClipSegment {
  id: number
  video_id: number
  start_seconds: number
  end_seconds: number
  duration_seconds?: number
  order_index: number
  order?: number
  label?: string | null
  note?: string | null
  created_at?: string
  updated_at?: string
}

export interface ClipSegmentCreatePayload {
  start_seconds: number
  end_seconds: number
  label?: string | null
  note?: string | null
  order_index?: number
}

export interface ClipSegmentUpdatePayload {
  start_seconds?: number
  end_seconds?: number
  label?: string | null
  note?: string | null
  order_index?: number
}

export interface VideoItem {
  id: number
  video_id?: number
  path: string
  filename: string
  size: number
  duration: number | null
  status: VideoStatus
  width?: number | null
  height?: number | null
  codec?: string | null
  fps?: number | null
  bit_rate?: number | null
  scan_error?: string | null
  scan_metadata?: Record<string, unknown> | null
  original_path?: string | null
  discarded_at?: string | null
  move_metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
  last_scanned_at: string
  clips?: ClipSegment[]
  current_path?: string
  decision?: string
}

export interface VideoListResponse {
  items: VideoItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export type ReviewDecision = "no_action" | "clip_selected"

export interface VideoFilterOptions {
  status?: VideoStatus | "all"
  page: number
  pageSize: number
  sortBy: string
  order: "desc" | "asc"
}

export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled"

export interface ProcessingJob {
  id: number
  video_id: number
  status: JobStatus
  progress: number
  message?: string | null
  error?: string | null
  strategy?: string | null
  output_path?: string | null
  archive_path?: string | null
  job_metadata?: Record<string, unknown> | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  updated_at: string
}

export interface ProcessingJobCreatePayload {
  force_reencode?: boolean
}
