import { describe, it, expect } from "vitest"
import { validateClipBounds } from "../src/lib/clipValidation"

describe("Clip bounds validation (validateClipBounds)", () => {
  it("passes for valid finite bounds within video duration", () => {
    const result = validateClipBounds(0, 10, 60)
    expect(result.isValid).toBe(true)
    expect(result.errors).toEqual({})
  })

  it("passes for float values with sub-second precision", () => {
    const result = validateClipBounds(12.5, 25.8, 100)
    expect(result.isValid).toBe(true)
    expect(result.errors).toEqual({})
  })

  it("fails when startSeconds is negative", () => {
    const result = validateClipBounds(-1, 10, 60)
    expect(result.isValid).toBe(false)
    expect(result.errors.start).toContain("起始时间不能为负数")
  })

  it("fails when endSeconds is negative", () => {
    const result = validateClipBounds(0, -5, 60)
    expect(result.isValid).toBe(false)
    expect(result.errors.end).toContain("结束时间不能为负数")
  })

  it("fails when values are NaN or non-finite", () => {
    const result1 = validateClipBounds(NaN, 10, 60)
    expect(result1.isValid).toBe(false)
    expect(result1.errors.start).toContain("起始时间必须为有限数值")

    const result2 = validateClipBounds(0, Infinity, 60)
    expect(result2.isValid).toBe(false)
    expect(result2.errors.end).toContain("结束时间必须为有限数值")
  })

  it("fails when endSeconds is less than or equal to startSeconds", () => {
    const resultEqual = validateClipBounds(10, 10, 60)
    expect(resultEqual.isValid).toBe(false)
    expect(resultEqual.errors.end).toContain("结束时间必须严格大于起始时间")

    const resultLess = validateClipBounds(15, 10, 60)
    expect(resultLess.isValid).toBe(false)
    expect(resultLess.errors.end).toContain("结束时间必须严格大于起始时间")
  })

  it("fails when endSeconds exceeds video duration", () => {
    const result = validateClipBounds(10, 65, 60)
    expect(result.isValid).toBe(false)
    expect(result.errors.end).toContain("不能超过视频总时长")
  })

  it("fails when startSeconds is at or beyond video duration", () => {
    const result = validateClipBounds(60, 70, 60)
    expect(result.isValid).toBe(false)
    expect(result.errors.start).toContain("不能超过或等于视频总时长")
  })

  it("works when video duration is null or not provided", () => {
    const result = validateClipBounds(10, 100, null)
    expect(result.isValid).toBe(true)
  })
})
