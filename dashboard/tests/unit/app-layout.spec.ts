import { createPinia, setActivePinia } from "pinia"
import { mount } from "@vue/test-utils"
import { describe, expect, it, beforeEach } from "vitest"
import AppLayout from "@/app/layouts/AppLayout.vue"

describe("AppLayout", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("仅提示最终计划提交关闭，不把真实环境误称为 Dry Run", () => {
    const wrapper = mount(AppLayout, {
      global: {
        stubs: {
          AppSidebar: { template: "<aside />" },
          AppTopbar: { template: "<header />" },
          RouterView: { template: "<main />" }
        }
      }
    })

    expect(wrapper.text()).toContain("最终计划提交已关闭")
    expect(wrapper.text()).not.toContain("Dry Run")
  })
})
