/**
 * Clip segment validation utilities.
 * Validates finite non-negative values, end > start, and end <= video duration.
 */

export interface ClipValidationErrors {
  start?: string
  end?: string
  general?: string
}

export interface ClipValidationResult {
  isValid: boolean
  errors: ClipValidationErrors
}

export function validateClipBounds(
  startSeconds: number,
  endSeconds: number,
  videoDuration?: number | null
): ClipValidationResult {
  const errors: ClipValidationErrors = {}

  // 1. 验证有限性 (finite)
  if (!Number.isFinite(startSeconds)) {
    errors.start = "起始时间必须为有限数值"
  } else if (startSeconds < 0) {
    // 2. 验证非负 (non-negative)
    errors.start = "起始时间不能为负数 (需 >= 0)"
  }

  if (!Number.isFinite(endSeconds)) {
    errors.end = "结束时间必须为有限数值"
  } else if (endSeconds < 0) {
    errors.end = "结束时间不能为负数 (需 >= 0)"
  }

  // 3. 仅在两个数值均有效且非负时，验证端点关系 end > start 与时长限制
  if (!errors.start && !errors.end) {
    if (endSeconds <= startSeconds) {
      errors.end = "结束时间必须严格大于起始时间"
    }

    // 4. 验证不超过视频时长 end <= video duration
    if (videoDuration != null && Number.isFinite(videoDuration) && videoDuration > 0) {
      if (endSeconds > videoDuration) {
        errors.end = `结束时间 (${endSeconds}s) 不能超过视频总时长 (${videoDuration}s)`
      }
      if (startSeconds >= videoDuration) {
        errors.start = `起始时间 (${startSeconds}s) 不能超过或等于视频总时长 (${videoDuration}s)`
      }
    }
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  }
}
