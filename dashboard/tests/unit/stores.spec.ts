import { describe, it, expect, vi, beforeEach } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useTaskStore } from "@/app/stores/task"
import { useQueueStore } from "@/app/stores/queue"
import { usePlanStore } from "@/app/stores/plan"
import { useRuleStore } from "@/app/stores/rule"
import { useAccountStore } from "@/app/stores/account"
import { useExceptionStore } from "@/app/stores/exception"

function okJson(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response
}

function failJson(status = 500): Response {
  return {
    ok: false,
    status,
    json: async () => ({ detail: { code: "INTERNAL", message: "服务异常" } })
  } as Response
}

function stubFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn()
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

describe("useTaskStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("fetchTasks 成功加载列表并清理错误", async () => {
    const fetchMock = stubFetch()
    const payload = [
      {
        id: "t1",
        drama_name: "剧A",
        platform: "番茄",
        available_time: "2026-08-06T10:00:00",
        status: "pending",
        owner: null,
        queue_state: null,
        updated_at: "2026-08-06T09:00:00"
      }
    ]
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useTaskStore()
    await store.fetchTasks({ date: "2026-08-06" })

    expect(store.tasks).toEqual(payload)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it("fetchTasks 失败时写入错误态", async () => {
    const fetchMock = stubFetch()
    fetchMock.mockResolvedValue(failJson())

    const store = useTaskStore()
    await store.fetchTasks()

    expect(store.tasks).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.error).toContain("服务异常")
  })

  it("fetchTask 成功写入详情", async () => {
    const fetchMock = stubFetch()
    const payload = {
      id: "t1",
      drama_name: "剧A",
      platform: "番茄",
      available_time: "2026-08-06T10:00:00",
      status: "pending",
      owner: null,
      queue_state: null,
      updated_at: "2026-08-06T09:00:00",
      queue_item_id: null,
      attempt_count: null,
      claimed_by: null,
      lease_until: null,
      ledger_id: null
    }
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useTaskStore()
    await store.fetchTask("t1")

    expect(store.detail).toEqual(payload)
  })

  it("enqueueTask 调用对应 API", async () => {
    const fetchMock = stubFetch()
    fetchMock.mockResolvedValue(okJson({ id: "q1", state: "WAITING_TIME" }))

    const store = useTaskStore()
    await store.enqueueTask("t1")

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/t1/enqueue",
      expect.objectContaining({ method: "POST" })
    )
  })
})

describe("useQueueStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("fetchQueue 按 state 过滤加载", async () => {
    const fetchMock = stubFetch()
    const payload = [
      {
        id: "q1",
        task_id: "t1",
        state: "PAUSED",
        priority: 0,
        available_at: "2026-08-06T10:00:00",
        claimed_by: null,
        lease_until: null,
        attempt_count: 0,
        next_run_at: null
      }
    ]
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useQueueStore()
    await store.fetchQueue("PAUSED")

    expect(store.items).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/queue?state=PAUSED",
      expect.anything()
    )
  })

  it("pause 携带 workerId", async () => {
    const fetchMock = stubFetch()
    fetchMock.mockResolvedValue(okJson({ id: "q1" }))

    const store = useQueueStore()
    await store.pause("q1", "w1")

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/queue/q1/pause",
      expect.objectContaining({ body: JSON.stringify({ worker_id: "w1" }) })
    )
  })
})

describe("usePlanStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("fetchPlans 将台账映射为计划视图", async () => {
    const fetchMock = stubFetch()
    fetchMock.mockResolvedValue(
      okJson([
        {
          id: "l1",
          task_id: "t1",
          drama_name: "剧A",
          platform: "番茄",
          final_status: "COMPLETED",
          completed_at: "2026-08-06T10:00:00"
        }
      ])
    )

    const store = usePlanStore()
    await store.fetchPlans()

    expect(store.plans).toEqual([
      {
        id: "l1",
        taskId: "t1",
        dramaName: "剧A",
        platform: "番茄",
        status: "COMPLETED",
        completedAt: "2026-08-06T10:00:00",
        taskName: "—",
        planType: "—",
        accountCount: "—",
        cidCount: "—",
        materialCount: "—",
        materialGroupCount: "—",
        expectedProjectCount: "—",
        ruleVersion: "—",
        validationStatus: "—",
        submitStatus: "—",
        externalTaskId: "—",
        createdAt: "—"
      }
    ])
  })
})

describe("useRuleStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("fetchRules 成功加载规则集", async () => {
    const fetchMock = stubFetch()
    const payload = [
      {
        id: "r1",
        key: "iap_price_2_9",
        name: "IAP 2.9 价格规则",
        category: "iap",
        status: "PUBLISHED",
        updated_at: "2026-08-06T08:00:00"
      }
    ]
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useRuleStore()
    await store.fetchRules()

    expect(store.ruleSets).toEqual(payload)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it("fetchRules 失败时写入错误态", async () => {
    const fetchMock = stubFetch()
    fetchMock.mockResolvedValue(failJson())

    const store = useRuleStore()
    await store.fetchRules()

    expect(store.ruleSets).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.error).toContain("服务异常")
  })

  it("fetchVersions 成功加载版本列表", async () => {
    const fetchMock = stubFetch()
    const payload = [
      {
        id: "v1",
        version: "1.0.0",
        status: "PUBLISHED",
        published_at: "2026-08-06T08:00:00"
      }
    ]
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useRuleStore()
    await store.fetchVersions("r1")

    expect(store.versions).toEqual(payload)
  })

  it("clearVersions 清空版本与错误", async () => {
    const fetchMock = stubFetch()
    fetchMock.mockResolvedValue(
      okJson([
        {
          id: "v1",
          version: "1.0.0",
          status: "PUBLISHED",
          published_at: "2026-08-06T08:00:00"
        }
      ])
    )

    const store = useRuleStore()
    await store.fetchVersions("r1")
    store.clearVersions()

    expect(store.versions).toEqual([])
    expect(store.error).toBeNull()
  })

  it("simulatePrice 返回模拟结果", async () => {
    const fetchMock = stubFetch()
    const payload = {
      inputs: [2.8, 3.0],
      outputs: [
        {
          candidate: 2.8,
          matched_rule_key: "iap_2_9",
          target_price: 2.9,
          distance: 0.1,
          selection_reason: "距离目标价最近"
        }
      ]
    }
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useRuleStore()
    const result = await store.simulatePrice([2.8, 3.0])

    expect(result).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/rules/simulate-price",
      expect.objectContaining({ body: JSON.stringify({ candidates: [2.8, 3.0] }) })
    )
  })
})

describe("useAccountStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("fetchOverview 成功加载账户概览", async () => {
    const fetchMock = stubFetch()
    const payload = {
      sync_status: "not_configured",
      last_synced_at: null,
      accounts: []
    }
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useAccountStore()
    await store.fetchOverview()

    expect(store.overview).toEqual(payload)
  })
})

describe("useExceptionStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("fetchExceptions 成功加载异常列表", async () => {
    const fetchMock = stubFetch()
    const payload = [
      {
        id: "e1",
        task_id: "t1",
        level: "ERROR",
        message: "登录失效",
        occurred_at: "2026-08-06T10:00:00"
      }
    ]
    fetchMock.mockResolvedValue(okJson(payload))

    const store = useExceptionStore()
    await store.fetchExceptions()

    expect(store.exceptions).toEqual(payload)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it("fetchExceptions 失败时写入错误态", async () => {
    const fetchMock = stubFetch()
    fetchMock.mockResolvedValue(failJson())

    const store = useExceptionStore()
    await store.fetchExceptions()

    expect(store.exceptions).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.error).toContain("服务异常")
  })
})
