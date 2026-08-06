import { describe, expect, it } from "vitest"
import { getStatusColor, getStatusLabel } from "@/shared/utils/status"
import {
  getLinkStatusMeta,
  getWorkflowNodeMeta
} from "@/entities/task/types"

describe("status-mapping", () => {
  it("后端任务状态映射为中文文案", () => {
    expect(getStatusLabel("WAITING_TIME")).toBe("等待时间")
    expect(getStatusLabel("READY")).toBe("准备完成")
    expect(getStatusLabel("QUEUED")).toBe("排队中")
    expect(getStatusLabel("RUNNING")).toBe("运行中")
    expect(getStatusLabel("RETRY_WAIT")).toBe("重试等待")
    expect(getStatusLabel("PAUSED")).toBe("已暂停")
    expect(getStatusLabel("MANUAL_REVIEW")).toBe("人工处理")
    expect(getStatusLabel("COMPLETED")).toBe("计划已完成")
    expect(getStatusLabel("FAILED")).toBe("失败")
    expect(getStatusLabel("CANCELLED")).toBe("已取消")
  })

  it("后端任务状态映射为状态颜色变量", () => {
    expect(getStatusColor("WAITING_TIME")).toContain("--color-status-pending")
    expect(getStatusColor("READY")).toContain("--color-status-pending")
    expect(getStatusColor("QUEUED")).toContain("--color-status-running")
    expect(getStatusColor("RUNNING")).toContain("--color-status-running")
    expect(getStatusColor("RETRY_WAIT")).toContain("--color-status-warning")
    expect(getStatusColor("PAUSED")).toContain("--color-status-paused")
    expect(getStatusColor("MANUAL_REVIEW")).toContain("--color-status-warning")
    expect(getStatusColor("COMPLETED")).toContain("--color-status-success")
    expect(getStatusColor("FAILED")).toContain("--color-status-failed")
    expect(getStatusColor("CANCELLED")).toContain("--color-status-pending")
  })

  it("工作流节点状态映射为文案与颜色", () => {
    expect(getWorkflowNodeMeta("done")).toEqual({
      label: "已完成",
      color: "var(--color-status-success)"
    })
    expect(getWorkflowNodeMeta("current").label).toBe("执行中")
    expect(getWorkflowNodeMeta("current").color).toContain(
      "--color-status-running"
    )
    expect(getWorkflowNodeMeta("pending").label).toBe("等待中")
    expect(getWorkflowNodeMeta("skipped").label).toBe("已跳过")
    expect(getWorkflowNodeMeta("failed").label).toBe("失败")
    expect(getWorkflowNodeMeta("failed").color).toContain(
      "--color-status-failed"
    )
  })

  it("推广链接状态映射为文案与颜色", () => {
    expect(getLinkStatusMeta("READY")).toEqual({
      label: "已就绪",
      color: "var(--color-status-success)"
    })
    expect(getLinkStatusMeta("CHECKING").label).toBe("检测中")
    expect(getLinkStatusMeta("FAILED").label).toBe("提取失败")
    expect(getLinkStatusMeta(null).label).toBe("未提取")
  })
})
