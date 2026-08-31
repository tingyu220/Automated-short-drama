import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import ErrorBoundary from "@/shared/ui/ErrorBoundary.vue"

describe("ErrorBoundary", () => {
  it("正常时渲染 slot 内容", () => {
    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: "<p>正常内容</p>"
      }
    })

    expect(wrapper.text()).toContain("正常内容")
  })

  it("子组件渲染异常时展示 ErrorState", async () => {
    const BrokenChild = {
      name: "BrokenChild",
      render() {
        throw new Error("渲染崩溃")
      }
    }

    const wrapper = mount(ErrorBoundary, {
      global: {
        components: { BrokenChild }
      },
      slots: {
        default: "<BrokenChild />"
      }
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain("渲染崩溃")
  })

  it("点击重试后恢复 slot 渲染", async () => {
    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: "<p>正常内容</p>"
      }
    })

    const vm = wrapper.vm as any
    vm.error = new Error("模拟异常")
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain("模拟异常")

    await wrapper.find("button").trigger("click")
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain("正常内容")
  })
})
