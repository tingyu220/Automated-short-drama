import { describe, expect, it, vi, afterEach } from "vitest"
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import AppTopbar from "@/app/layouts/AppTopbar.vue"

function healthResponse(environmentSwitching: boolean) {
  return {
    ok: true,
    json: () => Promise.resolve({
      environment: "REAL",
      worker_environment: environmentSwitching ? "MOCK" : "REAL",
      environment_switching: environmentSwitching,
      allow_final_submit: false,
      worker_heartbeat: true,
      database: "ok",
      config: "ok"
    })
  }
}

describe("AppTopbar", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("切换期间轮询健康状态，Worker 生效后移除切换中提示", async () => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(healthResponse(true))
      .mockResolvedValueOnce(healthResponse(false))

    const wrapper = mount(AppTopbar, {
      global: {
        stubs: {
          ElButton: { template: "<button><slot /></button>" },
          ElButtonGroup: { template: "<span><slot /></span>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()
    expect(wrapper.text()).toContain("切换中")

    await vi.advanceTimersByTimeAsync(1000)
    expect(wrapper.text()).not.toContain("切换中")
    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it("首次读取离线后会持续刷新为在线", async () => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          environment: "REAL",
          worker_environment: "REAL",
          environment_switching: false,
          allow_final_submit: false,
          worker_heartbeat: false,
          database: "ok",
          config: "ok"
        })
      })
      .mockResolvedValueOnce(healthResponse(false))

    const wrapper = mount(AppTopbar, {
      global: {
        stubs: {
          ElButton: { template: "<button><slot /></button>" },
          ElButtonGroup: { template: "<span><slot /></span>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()
    expect(wrapper.text()).toContain("离线")
    await vi.advanceTimersByTimeAsync(1000)
    expect(wrapper.text()).toContain("在线")
    wrapper.unmount()
  })

  it("明确展示 Worker 运行模式和当前生效模式", async () => {
    setActivePinia(createPinia())
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        environment: "REAL",
        worker_environment: "MOCK",
        environment_switching: true,
        allow_final_submit: false,
        worker_heartbeat: true,
        database: "ok",
        config: "ok"
      })
    })

    const wrapper = mount(AppTopbar, {
      global: {
        stubs: {
          ElButton: { template: "<button><slot /></button>" },
          ElButtonGroup: { template: "<span><slot /></span>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()
    expect(wrapper.text()).toContain("Worker运行模式")
    expect(wrapper.text()).toContain("目标：真实")
    expect(wrapper.text()).toContain("生效：模拟")
    wrapper.unmount()
  })

  it("真实 Worker 但最终提交保护开启时明确提示保护状态", async () => {
    setActivePinia(createPinia())
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        environment: "REAL",
        worker_environment: "REAL",
        environment_switching: false,
        allow_final_submit: false,
        worker_heartbeat: true,
        database: "ok",
        config: "ok"
      })
    })

    const wrapper = mount(AppTopbar, {
      global: {
        stubs: {
          ElButton: { template: "<button><slot /></button>" },
          ElButtonGroup: { template: "<span><slot /></span>" },
          ElIcon: { template: "<span><slot /></span>" }
        }
      }
    })

    await flushPromises()
    expect(wrapper.text()).toContain("真实链路 / 提交保护")
    wrapper.unmount()
  })
})
