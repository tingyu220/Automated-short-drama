import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import WorkflowTimeline from "@/widgets/workflow-timeline/WorkflowTimeline.vue"
import {
  buildWorkflowSteps,
  getWorkflowNodeMeta,
  queueStateToStep,
  type WorkflowStepNode
} from "@/entities/task/types"

describe("WorkflowTimeline", () => {
  const steps: WorkflowStepNode[] = [
    { key: "feishu", label: "飞书", status: "done" },
    { key: "link", label: "链接", status: "done" },
    { key: "resource", label: "剧目资源", status: "current" },
    { key: "config", label: "推广配置", status: "pending" },
    { key: "product", label: "产品库", status: "skipped" },
    { key: "planspec", label: "PlanSpec", status: "failed" },
    { key: "submit", label: "提交", status: "pending" },
    { key: "confirm", label: "状态确认", status: "pending" }
  ]

  it("渲染全部节点并标记当前节点", () => {
    const wrapper = mount(WorkflowTimeline, { props: { steps } })
    expect(wrapper.findAll(".workflow-timeline__node")).toHaveLength(
      steps.length
    )
    const current = wrapper.find(".workflow-timeline__node.is-current")
    expect(current.exists()).toBe(true)
    expect(current.attributes("aria-current")).toBe("step")
    expect(current.text()).toContain("剧目资源")
  })

  it("节点状态映射与高亮类一致", () => {
    const wrapper = mount(WorkflowTimeline, { props: { steps } })
    expect(wrapper.find(".is-done").exists()).toBe(true)
    expect(wrapper.find(".is-failed").exists()).toBe(true)
    expect(wrapper.find(".is-skipped").exists()).toBe(true)
    expect(wrapper.find(".is-pending").exists()).toBe(true)

    for (const step of steps) {
      const meta = getWorkflowNodeMeta(step.status)
      const node = wrapper
        .findAll(".workflow-timeline__node")
        .find((item) => item.text().includes(step.label))
      expect(node?.classes()).toContain(`is-${step.status}`)
      expect(meta.label.length).toBeGreaterThan(0)
    }
  })

  it("buildWorkflowSteps 生成默认轨道并高亮当前步骤", () => {
    const built = buildWorkflowSteps("config")
    expect(built.map((step) => step.key)).toEqual([
      "feishu",
      "link",
      "resource",
      "config",
      "product",
      "planspec",
      "submit",
      "confirm"
    ])
    expect(built.filter((step) => step.status === "done")).toHaveLength(3)
    expect(built.find((step) => step.key === "config")?.status).toBe("current")
    expect(built.find((step) => step.key === "product")?.status).toBe("pending")
  })

  it("queueStateToStep 将队列状态映射到工作流阶段", () => {
    expect(queueStateToStep("QUEUED")).toBe("feishu")
    expect(queueStateToStep("CLAIMED")).toBe("resource")
    expect(queueStateToStep("RUNNING")).toBe("config")
    expect(queueStateToStep("running")).toBe("config")
    expect(queueStateToStep("PAUSED")).toBeNull()
    expect(queueStateToStep(null)).toBeNull()
  })
})
