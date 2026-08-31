import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import TaskControlMenu from "@/features/task-control/TaskControlMenu.vue"
import type { TaskView } from "@/entities/task/types"

const task = (queue_state: string): TaskView => ({
  id: "t1",
  drama_name: "测试剧",
  platform: "TOMATO",
  end_type: "NATIVE",
  available_time: "2026-08-06T10:00:00",
  status: queue_state,
  owner: null,
  queue_state,
  updated_at: "2026-08-06T09:00:00",
  current_stage: "PROMOTION_CONFIG",
  target_stage: "LINK_READY",
  current_step: "config",
  iaa: "READY",
  price_9_9: "READY",
  price_2_9: "READY",
  album_id: "A-1001",
  product_library: "P-88",
  plan_spec: "PLAN-1",
  plan_status: "READY"
})

describe("TaskControlMenu", () => {
  it("演练完成任务不提供暂停和取消", async () => {
    const wrapper = mount(TaskControlMenu, { props: { task: task("DRY_RUN") } })

    await wrapper.get('[aria-label="更多操作"]').trigger("click")
    expect(document.body.textContent).toContain("手动入队")
    expect(document.body.textContent).not.toContain("取消任务")
    expect(document.body.textContent).not.toContain("暂停")
  })
})
