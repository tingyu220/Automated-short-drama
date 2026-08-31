import { describe, expect, it, vi } from "vitest"
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import WorkspacePage from "@/pages/workspace/index.vue"

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn() })
}))

describe("工作台 Session 状态", () => {
  it("首页将当前任务下方空间用于待处理队列、今日概览和最近活动", async () => {
    setActivePinia(createPinia())
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }))
    )

    const wrapper = mount(WorkspacePage, {
      global: {
        stubs: {
          TaskOverviewGrid: { template: "<div />" },
          CurrentTaskPanel: { template: "<div />" },
          TaskDetailDrawer: { template: "<div />" },
          EmptyState: { template: "<div />" },
          StatusDot: { template: "<span />" },
          ElButton: { template: "<button><slot /></button>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()
    expect(wrapper.find(".workspace__current").exists()).toBe(true)
    expect(wrapper.find(".workspace__operations").exists()).toBe(true)
    expect(wrapper.find(".workspace__activity").exists()).toBe(true)
    expect(wrapper.text()).toContain("待处理队列")
    expect(wrapper.text()).toContain("今日运行概览")
    expect(wrapper.text()).toContain("最近活动")
    wrapper.unmount()
  })

  it("当前任务支持打开平台和查看详情", async () => {
    setActivePinia(createPinia())
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null)
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL) => {
        const url = String(input)
        if (url.includes("/sessions")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                feishu: { status: "logged_in", login_url: "https://feishu.test" },
                tomato: { status: "logged_in", login_url: "https://tomato.test" },
                delivery: { status: "logged_in", login_url: "https://delivery.test" },
                ocean: { status: "logged_in", login_url: "https://ocean.test" }
              })
          })
        }
        if (url.includes("/tasks")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve([
                {
                  id: "task-1",
                  drama_name: "测试剧",
                  platform: "TOMATO",
                  available_time: "2026-08-19T10:00:00Z",
                  status: "RUNNING",
                  owner: null,
                  queue_state: "RUNNING",
                  current_stage: "LINK_EXTRACTION",
                  target_stage: "LINK_READY",
                  updated_at: "2026-08-19T10:00:00Z"
                }
              ])
          })
        }
        if (url.includes("/queue")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve([
                {
                  id: "queue-1",
                  task_id: "task-1",
                  state: "RUNNING",
                  priority: 1,
                  available_at: "2026-08-19T10:00:00Z",
                  claimed_by: "worker-1",
                  lease_until: "2099-01-01T00:00:00Z",
                  attempt_count: 1,
                  next_run_at: null,
                  failure_code: null,
                  retry_safe: false
                }
              ])
          })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
      })
    )

    const wrapper = mount(WorkspacePage, {
      global: {
        stubs: {
          TaskOverviewGrid: { template: "<div />" },
          CurrentTaskPanel: {
            template:
              '<div><button data-testid="open-platform" @click="$emit(\'open-platform\')">打开平台</button><button data-testid="view-task" @click="$emit(\'view\')">查看详情</button></div>'
          },
          TaskDetailDrawer: { template: "<div data-testid=\"task-detail\" />" },
          EmptyState: { template: "<div />" },
          StatusDot: { template: "<span />" },
          ElButton: { template: "<button><slot /></button>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()
    await wrapper.get('[data-testid="open-platform"]').trigger("click")
    expect(openSpy).toHaveBeenCalledWith("https://tomato.test", "_blank", "noopener,noreferrer")
    await wrapper.get('[data-testid="view-task"]').trigger("click")
    expect(wrapper.find('[data-testid="task-detail"]').exists()).toBe(true)
    openSpy.mockRestore()
    wrapper.unmount()
  })

  it("已登录平台旁边仍提供检测入口", async () => {
    setActivePinia(createPinia())
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL, init?: RequestInit) => {
        const url = String(input)
        if (init?.method === "POST") {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                platform: "delivery",
                status: "logged_in",
                message: "本地 Session 已持久化并校验"
              })
          })
        }
        if (url.includes("/sessions")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                feishu: { status: "logged_in" },
                tomato: { status: "logged_in" },
                delivery: { status: "logged_in" },
                ocean: { status: "logged_in" }
              })
          })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
      })
    )

    const wrapper = mount(WorkspacePage, {
      global: {
        stubs: {
          TaskOverviewGrid: { template: "<div />" },
          CurrentTaskPanel: { template: "<div />" },
          EmptyState: { template: "<div />" },
          StatusDot: { template: "<span />" },
          ElButton: { template: "<button><slot /></button>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()

    expect(wrapper.findAll(".resource-item__check")).toHaveLength(4)
    expect(wrapper.text()).toContain("检测")
    await wrapper.findAll(".resource-item__check")[2].trigger("click")
    await flushPromises()
    expect(wrapper.text()).toContain("检测完成：已登录")
    wrapper.unmount()
  })

  it("Chrome 导入失败时显示具体原因", async () => {
    setActivePinia(createPinia())
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL, init?: RequestInit) => {
        const url = String(input)
        if (init?.method === "POST" && url.includes("/chrome-import")) {
          return Promise.resolve({
            ok: false,
            status: 400,
            json: () => Promise.resolve({ detail: "Chrome 正在使用 Cookies" })
          })
        }
        if (url.includes("/sessions")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                feishu: { status: "logged_in" },
                tomato: { status: "needs_login" },
                delivery: { status: "needs_login" },
                ocean: { status: "needs_login" }
              })
          })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
      })
    )

    const wrapper = mount(WorkspacePage, {
      global: {
        stubs: {
          TaskOverviewGrid: { template: "<div />" },
          CurrentTaskPanel: { template: "<div />" },
          EmptyState: { template: "<div />" },
          StatusDot: { template: "<span />" },
          ElButton: { template: "<button><slot /></button>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()
    const chromeButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Chrome导入")
    expect(chromeButton).toBeDefined()
    await chromeButton!.trigger("click")
    await flushPromises()

    expect(wrapper.text()).toContain("Chrome 导入失败：Chrome 正在使用 Cookies")
    wrapper.unmount()
  })
})
