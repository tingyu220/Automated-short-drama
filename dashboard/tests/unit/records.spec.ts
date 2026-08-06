import { describe, expect, it, vi, beforeEach } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { mount, flushPromises } from "@vue/test-utils"
import { ElTabs, ElTabPane } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import RecordsPage from "@/pages/records/index.vue"
import { formatLedgerRow, toLedgerView } from "@/shared/utils/format"

function okJson(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response
}

const TEST_GLOBAL = {
  components: { ElTabs, ElTabPane, ElIcon: Refresh }
}

function stubFetch(payloads: Record<string, unknown>): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes("/records/events")) return Promise.resolve(okJson(payloads.events))
    if (url.includes("/records/artifacts")) return Promise.resolve(okJson(payloads.artifacts))
    return Promise.resolve(okJson(payloads.ledgers))
  })
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

const ledgerPayload = {
  id: "l1",
  task_id: "t1",
  drama_name: "测试剧",
  platform: "番茄",
  final_status: "COMPLETED",
  completed_at: "2026-08-06T10:05:00",
  album_id: "alb-100",
  product_id: "prod-200",
  external_task_id: "EXT-300",
  task_name: "番茄#端免测试剧20260806-100000-1",
  rule_version: "3",
  config_version: "7",
  feishu_row: "12"
}

describe("台账字段格式化", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("台账视图映射关键字段并格式化时间", () => {
    const view = toLedgerView(ledgerPayload)
    expect(view).toMatchObject({
      dramaName: "测试剧",
      feishuRow: "12",
      albumId: "alb-100",
      productId: "prod-200",
      externalTaskId: "EXT-300",
      taskName: "番茄#端免测试剧20260806-100000-1",
      ruleVersion: "3",
      configVersion: "7"
    })
    expect(formatLedgerRow(ledgerPayload).completedAt).toContain("2026-08-06 10:05")
  })

  it("缺失字段显示占位符", () => {
    const row = formatLedgerRow({
      id: "l2",
      task_id: "t2",
      drama_name: "测试剧2",
      platform: "剧变",
      final_status: "MANUAL_REVIEW",
      completed_at: null
    })
    expect(row.albumId).toBe("—")
    expect(row.externalTaskId).toBe("—")
    expect(row.configVersion).toBe("—")
    expect(row.completedAt).toBe("—")
  })
})

describe("RecordsPage", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.unstubAllGlobals()
  })

  it("业务台账渲染字段、状态与格式化时间", async () => {
    stubFetch({
      ledgers: [ledgerPayload],
      events: [],
      artifacts: []
    })
    const wrapper = mount(RecordsPage, {
      global: TEST_GLOBAL
    })
    await flushPromises()

    expect(wrapper.text()).toContain("测试剧")
    expect(wrapper.text()).toContain("EXT-300")
    expect(wrapper.text()).toContain("2026-08-06 10:05")
    expect(wrapper.text()).toContain("已完成")
  })

  it("无台账数据时渲染空态", async () => {
    stubFetch({ ledgers: [], events: [], artifacts: [] })
    const wrapper = mount(RecordsPage, {
      global: TEST_GLOBAL
    })
    await flushPromises()

    expect(wrapper.find(".empty-state").exists()).toBe(true)
    expect(wrapper.text()).toContain("暂无系统记录")
  })

  it("截图与文件页使用 ArtifactViewer 空态", async () => {
    stubFetch({
      ledgers: [],
      events: [
        {
          id: "ev1",
          task_id: "t1",
          event_type: "step_started",
          level: "INFO",
          message: "开始执行",
          context_json: null,
          occurred_at: "2026-08-06T09:00:00"
        }
      ],
      artifacts: []
    })
    const wrapper = mount(RecordsPage, {
      global: TEST_GLOBAL
    })
    await flushPromises()

    const tabButton = wrapper
      .findAll("[role='tab']")
      .find((tab) => tab.text().includes("截图与文件"))
    expect(tabButton).toBeTruthy()
    await tabButton?.trigger("click")
    await flushPromises()

    expect(wrapper.text()).toContain("暂无截图与文件")
  })
})
