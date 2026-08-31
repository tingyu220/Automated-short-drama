import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import RuleEditor from "@/features/rule-editor/RuleEditor.vue"

const rows = Array.from({ length: 12 }, (_, index) => ({
  id: index + 1,
  preview_name: `广告预设 ${index + 1}`,
  delivery_way: "标准投放",
  promotion_type: "端原生"
}))

describe("RuleEditor", () => {
  it("素材规则支持新增自定义区间", async () => {
    const wrapper = mount(RuleEditor, {
      props: { category: "material", ruleSets: [], materialRules: [] }
    })

    await wrapper.get("button[data-test='add-material-rule']").trigger("click")

    expect(wrapper.findAll("tbody tr")).toHaveLength(1)
  })

  it("广告预设列表默认分页展示，并显示总条数", () => {
    const wrapper = mount(RuleEditor, {
      props: {
        category: "adPreset",
        ruleSets: [],
        adPresets: rows
      }
    })

    expect(wrapper.findAll("tbody tr")).toHaveLength(10)
    expect(wrapper.text()).toContain("共 12 条")
  })

  it("CID 映射可从候选中选择，也可手动输入抖音号", () => {
    const wrapper = mount(RuleEditor, {
      props: {
        category: "cid",
        ruleSets: [],
        mappingProposal: [
          {
            cid: "1001",
            group: "B1",
            company: "主体A",
            pay_type: "IAP",
            account_count: 1,
            ad_preset: "",
            open_preset: "",
            douyin_account: "",
            ad_preset_candidates: ["广告预设A"],
            open_preset_candidates: ["开户预设A"]
          }
        ]
      }
    })

    expect(wrapper.findAll("input").length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain("广告预设A")
    expect(wrapper.text()).toContain("开户预设A")
  })
})
