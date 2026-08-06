import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import ExceptionPanel from "@/features/exception-resolution/ExceptionPanel.vue"
import type { ExceptionItem } from "@/app/stores/exception"
import {
  classifyException,
  getExceptionCategoryMeta,
  getRiskMeta,
  EXCEPTION_CATEGORIES
} from "@/shared/utils/format"

function makeItem(overrides: Partial<ExceptionItem> = {}): ExceptionItem {
  return {
    id: "e1",
    task_id: "t1",
    drama_name: "测试剧",
    platform: "番茄",
    step: "提交",
    error_type: "AUTH",
    level: "ERROR",
    message: "登录状态失效，需要重新登录",
    occurred_at: "2026-08-06T10:00:00",
    retry_count: 2,
    risk: "high",
    risk_label: "高风险",
    risk_color: "var(--color-status-failed)",
    category: "login_required",
    category_label: "需要重新登录",
    stack_trace: "Traceback ...",
    ...overrides
  }
}

describe("exception 分类与风险映射", () => {
  it("八个分类均有中文文案", () => {
    expect(EXCEPTION_CATEGORIES).toHaveLength(8)
    for (const category of EXCEPTION_CATEGORIES) {
      const meta = getExceptionCategoryMeta(category.key)
      expect(meta.label).toBe(category.label)
      expect(meta.risk).toBe(category.risk)
      expect(meta.risk_label.length).toBeGreaterThan(0)
      expect(meta.risk_color).toContain("--color-")
    }
  })

  it("分类到文案/风险等级映射正确", () => {
    expect(getExceptionCategoryMeta("login_required").label).toBe("需要重新登录")
    expect(getExceptionCategoryMeta("login_required").risk).toBe("high")
    expect(getExceptionCategoryMeta("config_missing").label).toBe("需要配置补充")
    expect(getExceptionCategoryMeta("config_missing").risk).toBe("medium")
    expect(getExceptionCategoryMeta("manual_review").label).toBe("需要人工核对")
    expect(getExceptionCategoryMeta("auto_retry").label).toBe("可以自动重试")
    expect(getExceptionCategoryMeta("auto_retry").risk).toBe("low")
    expect(getExceptionCategoryMeta("page_changed").label).toBe("页面可能改版")
    expect(getExceptionCategoryMeta("result_uncertain").label).toBe("结果不确定")
    expect(getExceptionCategoryMeta("account_structure").label).toBe("账户表结构异常")
    expect(getExceptionCategoryMeta("feishu_partial_write").label).toBe("飞书部分写入")
  })

  it("按消息关键词分类，未命中回退为人工核对", () => {
    expect(classifyException("登录态过期，请重新登录").key).toBe("login_required")
    expect(classifyException("缺少推广配置").key).toBe("config_missing")
    expect(classifyException("页面结构可能发生变化").key).toBe("page_changed")
    expect(classifyException("任务进入人工复核").key).toBe("manual_review")
    expect(classifyException("未知异常内容").key).toBe("manual_review")
  })

  it("风险等级映射为文案与颜色", () => {
    expect(getRiskMeta("high")).toMatchObject({
      label: "高风险",
      color: "var(--color-status-failed)"
    })
    expect(getRiskMeta("medium")).toMatchObject({
      label: "中风险",
      color: "var(--color-status-warning)"
    })
    expect(getRiskMeta("low")).toMatchObject({
      label: "低风险",
      color: "var(--color-status-pending)"
    })
  })
})

describe("ExceptionPanel", () => {
  it("渲染分类文案与风险等级，技术堆栈默认折叠", () => {
    const wrapper = mount(ExceptionPanel, {
      props: { items: [makeItem()], loading: false, error: null }
    })
    expect(wrapper.text()).toContain("测试剧")
    expect(wrapper.text()).toContain("需要重新登录")
    expect(wrapper.text()).toContain("高风险")

    const stack = wrapper.find(".exception-panel__stack")
    expect(stack.exists()).toBe(true)
    expect(stack.attributes("open")).toBeUndefined()
    expect(stack.text()).toContain("技术堆栈")
  })

  it("选择异常后显示详情区并触发操作事件", async () => {
    const wrapper = mount(ExceptionPanel, {
      props: { items: [makeItem()], loading: false, error: null }
    })
    const row = wrapper.find(".exception-panel__row")
    await row.trigger("click")
    expect(wrapper.text()).toContain("错误原因")
    expect(wrapper.text()).toContain("系统判断")

    const button = wrapper
      .findAll("button")
      .find((item) => item.text().includes("继续执行"))
    expect(button).toBeTruthy()
    await button?.trigger("click")
    expect(wrapper.emitted("action")).toEqual([
      [{ item: makeItem(), action: "continue" }]
    ])
  })

  it("无数据时渲染共享空态", () => {
    const wrapper = mount(ExceptionPanel, {
      props: { items: [], loading: false, error: null }
    })
    expect(wrapper.find(".empty-state").exists()).toBe(true)
    expect(wrapper.text()).toContain("暂无异常")
  })
})
