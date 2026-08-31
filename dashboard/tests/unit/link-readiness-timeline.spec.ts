import { describe, expect, it } from "vitest"
import { buildLinkReadinessStages } from "@/entities/task/types"

describe("链接准备阶段状态", () => {
  it("按当前阶段生成已完成、进行中和待处理状态", () => {
    const stages = buildLinkReadinessStages("DELIVERY_DRAMA", "RUNNING", [])

    expect(stages.map((stage) => stage.status)).toEqual([
      "done",
      "done",
      "current",
      "pending",
      "pending"
    ])
  })

  it("链接已就绪时五个阶段全部完成", () => {
    const stages = buildLinkReadinessStages("LINK_READY", "LINK_READY", [])

    expect(stages.every((stage) => stage.status === "done")).toBe(true)
  })

  it("历史完成任务按链接已就绪展示", () => {
    const stages = buildLinkReadinessStages(
      "WAITING_AVAILABLE_TIME",
      "COMPLETED",
      []
    )

    expect(stages.every((stage) => stage.status === "done")).toBe(true)
  })
})
