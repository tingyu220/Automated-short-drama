import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import RulePublishPanel from "@/features/rule-publish/RulePublishPanel.vue"

describe("RulePublishPanel", () => {
  it("版本记录展示所属规则集名称", () => {
    const wrapper = mount(RulePublishPanel, {
      props: {
        ruleSetId: "rules-material",
        ruleSetName: "素材规则",
        versions: [
          {
            id: "v2",
            version: "2",
            status: "PUBLISHED",
            published_at: "2026-08-17T18:00:00"
          }
        ]
      }
    })

    expect(wrapper.text()).toContain("素材规则")
    expect(wrapper.text()).toContain("v2")
  })
})
