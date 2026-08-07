import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import TaskTable from "@/widgets/task-table/TaskTable.vue"
import type { TaskView } from "@/entities/task/types"

const row: TaskView = {
  id: "t1",
  drama_name: "测试剧",
  platform: "番茄",
  available_time: "2026-08-06T10:00:00",
  status: "RUNNING",
  owner: null,
  queue_state: "RUNNING",
  updated_at: "2026-08-06T09:00:00",
  current_step: "config",
  iaa: "READY",
  price_9_9: "READY",
  price_2_9: "CHECKING",
  album_id: "A-1001",
  product_library: "P-88",
  plan_spec: "PLAN-1",
  plan_status: "READY"
}

describe("TaskTable", () => {
  it("加载态渲染骨架", () => {
    const wrapper = mount(TaskTable, {
      props: { rows: [], loading: true, error: null }
    })
    expect(wrapper.find(".loading-skeleton").exists()).toBe(true)
    expect(wrapper.get(".loading-skeleton").attributes("role")).toBe("status")
  })

  it("空态渲染 EmptyState", () => {
    const wrapper = mount(TaskTable, {
      props: { rows: [], loading: false, error: null }
    })
    expect(wrapper.text()).toContain("暂无任务")
  })

  it("错误态渲染 ErrorState 并支持重试", async () => {
    const wrapper = mount(TaskTable, {
      props: { rows: [], loading: false, error: "服务异常" }
    })
    expect(wrapper.text()).toContain("服务异常")
    await wrapper.find("button").trigger("click")
    expect(wrapper.emitted("retry")).toHaveLength(1)
  })

  it("渲染任务行并触发查看/继续/更多操作", async () => {
    const wrapper = mount(TaskTable, {
      props: { rows: [row], loading: false, error: null }
    })
    expect(wrapper.text()).toContain("测试剧")
    expect(wrapper.text()).toContain("番茄")

    const buttons = wrapper.findAll(".task-table__action-button")
    await buttons[0].trigger("click")
    expect(wrapper.emitted("view")).toHaveLength(1)
    await buttons[1].trigger("click")
    expect(wrapper.emitted("continue")).toHaveLength(1)

    const menu = wrapper.findComponent({ name: "TaskControlMenu" })
    expect(menu.exists()).toBe(true)
    await menu.vm.$emit("command", { task: row, action: "cancel" })
    expect(wrapper.emitted("command")).toEqual([
      [{ task: row, action: "cancel" }]
    ])
  })
})
