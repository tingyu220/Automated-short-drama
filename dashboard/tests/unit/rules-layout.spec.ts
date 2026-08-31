import { describe, expect, it } from "vitest"
import { rulesLayoutClass } from "@/pages/rules/layout"

describe("rulesLayoutClass", () => {
  it("价格模板保留模拟器列", () => {
    expect(rulesLayoutClass("price")).toBe("rules-page__layout--with-side")
  })

  it("其它规则页面占满主区域", () => {
    expect(rulesLayoutClass("material")).toBe("rules-page__layout--full")
  })
})
