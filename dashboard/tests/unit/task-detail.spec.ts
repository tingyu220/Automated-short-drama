import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import { ElSelect } from "element-plus"
import TaskDetailDrawer from "@/features/task-detail/TaskDetailDrawer.vue"
import type { TaskView } from "@/entities/task/types"

const task: TaskView = {
  id: "task-1",
  drama_name: "测试漫剧",
  platform: "TOMATO",
  end_type: "NATIVE",
  available_time: "2026-08-16T08:00:00Z",
  status: "LINK_READY",
  owner: null,
  queue_state: "COMPLETED",
  updated_at: "2026-08-16T08:05:00Z",
  current_stage: "LINK_READY",
  target_stage: "LINK_READY",
  link_set: {
    IAA: "aweme://iaa",
    "9.9": "aweme://iap-99"
  },
  delivery_drama_id: "dd-1",
  promotion_configs: {
    IAA: "iaa-番茄-测试漫剧",
    "9.9": "9.9-番茄-测试漫剧"
  }
}

describe("TaskDetailDrawer", () => {
  it("选择仅提取链接后按对应终点运行", async () => {
    const wrapper = mount(TaskDetailDrawer, {
      props: { open: true, task },
      global: {
        stubs: {
          ElDrawer: { template: "<div><slot /></div>" },
          "el-icon": true
        }
      }
    })
    wrapper.findComponent(ElSelect).vm.$emit(
      "update:modelValue",
      "LINK_EXTRACTION"
    )

    await wrapper.get('[aria-label="运行任务"]').trigger("click")

    expect(wrapper.emitted("run")).toEqual([["LINK_EXTRACTION"]])
  })

  it("展示链接就绪阶段和投放系统产物", () => {
    const wrapper = mount(TaskDetailDrawer, {
      props: { open: true, task },
      global: {
        stubs: {
          ElDrawer: { template: "<div><slot /></div>" },
          "el-icon": true
        }
      }
    })

    expect(wrapper.text()).toContain("链接已就绪")
    expect(wrapper.text()).toContain("投放剧目 ID")
    expect(wrapper.text()).toContain("dd-1")
    expect(wrapper.text()).toContain("iaa-番茄-测试漫剧")
    expect(wrapper.text()).toContain("9.9-番茄-测试漫剧")
    expect(wrapper.get('[aria-label="链接准备阶段进度"]').text()).toContain("搭建投放剧目")
    expect(wrapper.attributes("size")).toBe("min(820px, 100vw)")
  })
})
