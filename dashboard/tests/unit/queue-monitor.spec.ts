import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import QueueMonitor from "@/widgets/queue-monitor/QueueMonitor.vue"

describe("QueueMonitor", () => {
  it("队列项自带剧名时优先显示具体剧目", () => {
    const wrapper = mount(QueueMonitor, {
      props: {
        items: [
          {
            id: "q1",
            task_id: "missing-task",
            drama_name: "远海归潮",
            state: "MANUAL_REVIEW",
            priority: 0,
            available_at: "2026-08-17T17:26:00",
            claimed_by: null,
            lease_until: null,
            attempt_count: 0,
            next_run_at: null,
            failure_code: "LINK_NOT_READY",
            retry_safe: false
          }
        ],
        tasks: [],
        loading: false,
        error: null,
        worker: {
          online: true,
          heartbeatText: "正常",
          currentTask: "—",
          leaseUntil: "—",
          platform: "—",
          runtime: "—"
        }
      }
    })

    expect(wrapper.find(".queue-monitor__drama").text()).toBe("远海归潮")
  })
})
