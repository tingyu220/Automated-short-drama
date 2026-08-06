import { describe, it, expect } from "vitest"
import { getStatusLabel, getStatusColor } from "@/shared/utils/status"

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
})
