/**
 * Video review API client module.
 */

import {
  ClipSegment,
  ClipSegmentCreatePayload,
  ClipSegmentUpdatePayload,
  ReviewDecision,
  VideoItem,
  VideoListResponse,
  VideoStatus,
} from "@/types/video"

export interface FetchVideosParams {
  page?: number
  pageSize?: number
  status?: VideoStatus | "all"
  sortBy?: string
  order?: "desc" | "asc"
}

export async function fetchVideos(
  baseUrl: string,
  params: FetchVideosParams = {}
): Promise<VideoListResponse> {
  const {
    page = 1,
    pageSize = 20,
    status,
    sortBy = "duration",
    order = "desc",
  } = params

  const query = new URLSearchParams()
  query.set("page", page.toString())
  query.set("page_size", pageSize.toString())
  query.set("sort_by", sortBy)
  query.set("order", order)

  if (status && status !== "all") {
    query.set("status", status)
  }

  const url = `${baseUrl}/api/videos?${query.toString()}`
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      if (errorJson?.detail) {
        errorDetail = errorJson.detail
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(`获取视频列表失败: ${errorDetail}`)
  }

  return response.json()
}

export async function fetchVideoById(
  baseUrl: string,
  videoId: number
): Promise<VideoItem> {
  const url = `${baseUrl}/api/videos/${videoId}`
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      if (errorJson?.detail) errorDetail = errorJson.detail
    } catch {
      // ignore
    }
    throw new Error(`获取视频详情失败: ${errorDetail}`)
  }

  return response.json()
}

export async function recordDecision(
  baseUrl: string,
  videoId: number,
  decision: ReviewDecision
): Promise<VideoItem> {
  const url = `${baseUrl}/api/videos/${videoId}/decision`
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ decision }),
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      if (errorJson?.detail) errorDetail = errorJson.detail
    } catch {
      // ignore
    }
    throw new Error(`提交审核决策失败: ${errorDetail}`)
  }

  return response.json()
}

export function getVideoPreviewUrl(baseUrl: string, videoId: number): string {
  return `${baseUrl}/api/videos/${videoId}/preview`
}

export async function fetchVideoClips(
  baseUrl: string,
  videoId: number
): Promise<ClipSegment[]> {
  const url = `${baseUrl}/api/videos/${videoId}/clips`
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      if (errorJson?.detail) errorDetail = errorJson.detail
    } catch {
      // ignore
    }
    throw new Error(`获取片段列表失败: ${errorDetail}`)
  }

  return response.json()
}

export async function createVideoClip(
  baseUrl: string,
  videoId: number,
  payload: ClipSegmentCreatePayload
): Promise<ClipSegment> {
  const url = `${baseUrl}/api/videos/${videoId}/clips`
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      if (errorJson?.detail) errorDetail = errorJson.detail
    } catch {
      // ignore
    }
    throw new Error(`创建片段失败: ${errorDetail}`)
  }

  return response.json()
}

export async function updateVideoClip(
  baseUrl: string,
  videoId: number,
  clipId: number,
  payload: ClipSegmentUpdatePayload
): Promise<ClipSegment> {
  const url = `${baseUrl}/api/videos/${videoId}/clips/${clipId}`
  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      if (errorJson?.detail) errorDetail = errorJson.detail
    } catch {
      // ignore
    }
    throw new Error(`更新片段失败: ${errorDetail}`)
  }

  return response.json()
}

export async function deleteVideoClip(
  baseUrl: string,
  videoId: number,
  clipId: number
): Promise<void> {
  const url = `${baseUrl}/api/videos/${videoId}/clips/${clipId}`
  const response = await fetch(url, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
    },
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      if (errorJson?.detail) errorDetail = errorJson.detail
    } catch {
      // ignore
    }
    throw new Error(`删除片段失败: ${errorDetail}`)
  }
}

