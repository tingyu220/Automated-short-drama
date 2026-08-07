import { ApiError, toApiError } from "./error-handler"

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined
>

const API_BASE = "/api"

function buildUrl(path: string, params?: QueryParams): string {
  const query = new URLSearchParams()
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, String(value))
      }
    }
  }
  const queryString = query.toString()
  return queryString ? `${API_BASE}${path}?${queryString}` : `${API_BASE}${path}`
}

async function request<T>(url: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    throw toApiError(error)
  }

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      // 忽略空响应体，由错误类型映射兜底
    }
    throw toApiError(payload, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError("UNKNOWN", "响应解析失败，请稍后重试")
  }
}

export function apiGet<T>(path: string, params?: QueryParams): Promise<T> {
  return request<T>(buildUrl(path, params), { method: "GET" })
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(buildUrl(path), {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(buildUrl(path), {
    method: "PUT",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
}
