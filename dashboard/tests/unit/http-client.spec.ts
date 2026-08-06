import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { apiGet, apiPost } from "@/shared/api/http-client"
import { ApiError } from "@/shared/api/error-handler"

describe("http-client", () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("apiGet 拼接 /api 前缀并携带筛选参数", async () => {
    const payload = [{ id: "task-1", drama_name: "测试剧" }]
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload
    } as Response)

    const result = await apiGet<typeof payload>("/tasks", {
      date: "2026-08-06",
      platform: "番茄",
      q: ""
    })

    expect(result).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks?date=2026-08-06&platform=%E7%95%AA%E8%8C%84",
      expect.objectContaining({ method: "GET" })
    )
  })

  it("apiPost 发送 JSON 请求体", async () => {
    const payload = { id: "queue-1", state: "PAUSED" }
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload
    } as Response)

    const result = await apiPost<typeof payload>("/tasks/task-1/enqueue", {
      worker_id: "w1"
    })

    expect(result).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task-1/enqueue",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ worker_id: "w1" })
      })
    )
  })

  it("业务错误映射为 CONFIGURATION", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        detail: { code: "CONFIGURATION_ERROR", message: "缺少配置" }
      })
    } as Response)

    await expect(apiGet("/tasks")).rejects.toMatchObject({
      name: "ApiError",
      code: "CONFIGURATION",
      status: 400,
      message: "缺少配置"
    })
  })

  it("HTTP 401 映射为 AUTH", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({
        detail: { code: "LOGIN_REQUIRED", message: "登录状态失效" }
      })
    } as Response)

    await expect(apiGet("/tasks")).rejects.toMatchObject({
      code: "AUTH",
      status: 401
    })
  })

  it("业务 PAGE_CHANGED 优先级高于 HTTP 状态", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({
        detail: { code: "PAGE_CHANGED", message: "页面结构可能发生变化" }
      })
    } as Response)

    await expect(apiGet("/tasks")).rejects.toMatchObject({
      code: "PAGE_CHANGED",
      status: 500
    })
  })

  it("网络错误映射为 RETRYABLE", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"))

    await expect(apiGet("/tasks")).rejects.toMatchObject({
      code: "RETRYABLE"
    })
  })

  it("无业务信息的 404 映射为 UNKNOWN", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Not Found" })
    } as Response)

    const error = await apiGet("/tasks/not-found").catch((err: unknown) => err)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: "UNKNOWN", status: 404 })
  })

  it("204 无响应体时返回 undefined", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error("no body")
      }
    } as unknown as Response)

    await expect(apiPost("/queue/queue-1/pause")).resolves.toBeUndefined()
  })
})
