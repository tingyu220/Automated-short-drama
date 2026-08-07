import { describe, it, expect } from "vitest"
import { beforeEach, vi } from "vitest"
import { mount } from "@vue/test-utils"
import { setActivePinia, createPinia } from "pinia"
import { flushPromises } from "@vue/test-utils"
import RuleSimulator from "@/widgets/rule-simulator/RuleSimulator.vue"
import {
  parseCandidates,
  simulatePriceCandidates,
  type PriceRuleInput
} from "@/widgets/rule-simulator/simulator"

const rule29: PriceRuleInput = {
  key: "iap_2_9",
  name: "IAP 2.9",
  targetPrice: 2.9,
  minPrice: 2.6,
  maxPrice: 5,
  sameDistanceStrategy: "HIGHER_PRICE_FIRST",
  enabled: true
}

const rule99: PriceRuleInput = {
  key: "iap_9_9",
  name: "IAP 9.9",
  targetPrice: 9.9,
  minPrice: 8.8,
  maxPrice: 13.8,
  sameDistanceStrategy: "HIGHER_PRICE_FIRST",
  enabled: true
}

describe("simulatePriceCandidates", () => {
  it("区间内候选返回匹配、规则与距离", () => {
    const [row] = simulatePriceCandidates([3], [rule29, rule99])
    expect(row.matched).toBe(true)
    expect(row.matchedRuleKey).toBe("iap_2_9")
    expect(row.ruleName).toBe("IAP 2.9")
    expect(row.distance).toBeCloseTo(0.1)
    expect(row.selectionReason).toContain("距离")
  })

  it("区间外候选不匹配", () => {
    const [row] = simulatePriceCandidates([6], [rule29, rule99])
    expect(row.matched).toBe(false)
    expect(row.matchedRuleKey).toBeNull()
    expect(row.targetPrice).toBeNull()
    expect(row.selectionReason).toBe("NO_MATCH")
  })

  it("同距离优先高价", () => {
    const lower: PriceRuleInput = {
      key: "low",
      name: "低价模板",
      targetPrice: 10,
      minPrice: 8,
      maxPrice: 12,
      sameDistanceStrategy: "HIGHER_PRICE_FIRST",
      enabled: true
    }
    const higher: PriceRuleInput = {
      key: "high",
      name: "高价模板",
      targetPrice: 12,
      minPrice: 10,
      maxPrice: 14,
      sameDistanceStrategy: "HIGHER_PRICE_FIRST",
      enabled: true
    }
    const [row] = simulatePriceCandidates([11], [lower, higher])
    expect(row.matched).toBe(true)
    expect(row.matchedRuleKey).toBe("high")
    expect(row.distance).toBe(1)
  })

  it("保持输入顺序且禁用规则不参与匹配", () => {
    const disabled = { ...rule29, enabled: false }
    const rows = simulatePriceCandidates([2.8, 3], [rule29, rule99])
    expect(rows.map((row) => row.candidate)).toEqual([2.8, 3])
    const [noMatch] = simulatePriceCandidates([2.8], [disabled])
    expect(noMatch.matched).toBe(false)
  })
})

describe("parseCandidates", () => {
  it("解析中英文逗号与空白分隔的价格", () => {
    expect(parseCandidates("2.8, 3.0，4.9\n5.5")).toEqual([2.8, 3, 4.9, 5.5])
    expect(parseCandidates("abc, 2.8, , 3")).toEqual([2.8, 3])
  })
})

describe("RuleSimulator", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          inputs: [3],
          outputs: [
            {
              candidate: 3,
              matched_rule_key: "iap_2_9",
              target_price: 2.9,
              distance: 0.1,
              selection_reason: "距离目标价最近"
            }
          ]
        })
      } as Response)
    )
    vi.stubGlobal("fetch", fetchMock)
  })

  it("输入候选价格后渲染匹配结果", async () => {
    const wrapper = mount(RuleSimulator, {
      props: { rules: [rule29, rule99] }
    })
    await wrapper.find("input").setValue("3")
    await flushPromises()
    expect(wrapper.text()).toContain("匹配")
    expect(wrapper.text()).toContain("IAP 2.9")
    expect(wrapper.text()).toContain("0.10")
  })

  it("无规则时显示空态", () => {
    const wrapper = mount(RuleSimulator, {
      props: { rules: [] }
    })
    expect(wrapper.text()).toContain("暂无价格规则")
  })
})
