import { describe, it, expect, vi, beforeEach } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useSystemStore } from "@/app/stores/system"

describe("useSystemStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("默认 allowFinalSubmit 为 false", () => {
    const store = useSystemStore()
    expect(store.allowFinalSubmit).toBe(false)
  })

  it("fetchHealth 成功后更新状态", async () => {
    const mockResponse = {
      environment: "development",
      allow_final_submit: true,
      worker_heartbeat: "ok",
      database: "ok",
      config: { version: "1.0" }
    }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse)
    })
    const store = useSystemStore()
    await store.fetchHealth()
    expect(store.environment).toBe("development")
    expect(store.allowFinalSubmit).toBe(true)
    expect(store.workerHeartbeat).toBe("ok")
    expect(store.database).toBe("ok")
    expect(store.config).toEqual({ version: "1.0" })
  })

  it("fetchHealth 网络错误时不修改现有状态", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Network error"))
    const store = useSystemStore()
    store.environment = "production"
    await store.fetchHealth()
    expect(store.environment).toBe("production")
  })
})
