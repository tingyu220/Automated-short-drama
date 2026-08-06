import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import PlanSpecPreview from "@/widgets/plan-preview/PlanSpecPreview.vue"
import type { PlanView } from "@/app/stores/plan"

const plan: PlanView = {
  id: "l1",
  taskId: "t1",
  dramaName: "测试剧",
  platform: "番茄",
  status: "COMPLETED",
  completedAt: "2026-08-06T10:00:00",
  taskName: "番茄#端免测试剧20260806-100000-1",
  planType: "标准投放",
  accountCount: "10",
  cidCount: "3",
  materialCount: "12",
  materialGroupCount: "6",
  expectedProjectCount: "3",
  ruleVersion: "3",
  validationStatus: "VALIDATED",
  submitStatus: "SUBMITTED",
  externalTaskId: "EXT-1001",
  createdAt: "2026-08-06T09:00:00"
}

describe("PlanSpecPreview", () => {
  it("空态渲染暂无计划数据", () => {
    const wrapper = mount(PlanSpecPreview, {
      props: { plan: null, loading: false, error: null }
    })
    expect(wrapper.text()).toContain("暂无计划数据")
  })

  it("渲染结构化字段与状态", () => {
    const wrapper = mount(PlanSpecPreview, {
      props: { plan, loading: false, error: null }
    })
    expect(wrapper.text()).toContain("测试剧")
    expect(wrapper.text()).toContain("番茄#端免测试剧20260806-100000-1")
    expect(wrapper.text()).toContain("标准投放")
    expect(wrapper.text()).toContain("EXT-1001")
    expect(wrapper.text()).toContain("已完成")
    expect(wrapper.text()).toContain("10")
  })

  it("切换查看原始数据", async () => {
    const wrapper = mount(PlanSpecPreview, {
      props: { plan, loading: false, error: null }
    })
    const toggle = wrapper
      .findAll("button")
      .find((button) => button.text().includes("查看原始数据"))
    expect(toggle).toBeTruthy()
    await toggle?.trigger("click")
    expect(wrapper.find("pre").exists()).toBe(true)
    expect(wrapper.text()).toContain('"taskName"')
    expect(wrapper.text()).toContain('"externalTaskId"')
  })
})
