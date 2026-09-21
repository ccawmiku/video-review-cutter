import "@testing-library/jest-dom"
import { vi } from "vitest"

if (typeof window !== "undefined" && window.HTMLMediaElement) {
  window.HTMLMediaElement.prototype.play = vi.fn().mockImplementation(() => Promise.resolve())
  window.HTMLMediaElement.prototype.pause = vi.fn().mockImplementation(() => {})
}
