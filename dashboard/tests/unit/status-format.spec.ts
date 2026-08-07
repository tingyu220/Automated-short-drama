import { describe, it, expect } from "vitest"
import {
  getStatusLabel,
  getStatusColor,
  getPlatformLabel
} from "@/shared/utils/status"

describe("status-format", () => {
  it("getStatusLabel 返回对应的中文文案", () => {
    expect(getStatusLabel("pending")).toBe("未开始")
    expect(getStatusLabel("running")).toBe("运行中")
    expect(getStatusLabel("success")).toBe("已完成")
    expect(getStatusLabel("failed")).toBe("失败")
    expect(getStatusLabel("paused")).toBe("已暂停")
    expect(getStatusLabel("cancelled")).toBe("已取消")
  })

  it("getStatusColor 返回对应的 CSS 变量", () => {
    expect(getStatusColor("pending")).toContain("--color-status-pending")
    expect(getStatusColor("running")).toContain("--color-status-running")
    expect(getStatusColor("success")).toContain("--color-status-success")
    expect(getStatusColor("failed")).toContain("--color-status-failed")
    expect(getStatusColor("paused")).toContain("--color-status-paused")
  })

  it("未知状态返回默认文案", () => {
    expect(getStatusLabel("unknown" as never)).toBe("未知")
  })

  it("平台代码映射为中文标签", () => {
    expect(getPlatformLabel("TOMATO")).toBe("番茄")
    expect(getPlatformLabel("JUBIAN")).toBe("剧变")
    expect(getPlatformLabel("unknown")).toBe("unknown")
    expect(getPlatformLabel(null)).toBe("—")
  })
})
