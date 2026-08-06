import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import StatusDot from "@/shared/ui/StatusDot.vue"

describe("StatusDot", () => {
  it("active 支持字符串 true 且忽略大小写", () => {
    const wrapper = mount(StatusDot, { props: { active: "TRUE" } })
    expect(wrapper.find(".status-dot").classes()).toContain("is-active")
  })

  it("非 active 值不高亮", () => {
    const wrapper = mount(StatusDot, { props: { active: "False" } })
    expect(wrapper.find(".status-dot").classes()).not.toContain("is-active")
  })
})
