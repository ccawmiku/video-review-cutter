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
  duration_seconds: number
  order_index: number
  label?: string | null
  created_at?: string
  updated_at?: string
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
