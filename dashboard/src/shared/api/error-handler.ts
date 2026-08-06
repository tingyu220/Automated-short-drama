export type ApiErrorCode =
  | "CONFIGURATION"
  | "AUTH"
  | "PAGE_CHANGED"
  | "RETRYABLE"
  | "UNKNOWN"

export const ERROR_MESSAGES: Record<ApiErrorCode, string> = {
  CONFIGURATION: "缺少配置",
  AUTH: "登录状态失效",
  PAGE_CHANGED: "页面结构可能发生变化",
  RETRYABLE: "临时错误，可重试",
  UNKNOWN: "请求失败，请稍后重试"
}

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status?: number

  constructor(code: ApiErrorCode, message?: string, status?: number) {
    super(message ?? ERROR_MESSAGES[code])
    this.name = "ApiError"
    this.code = code
    if (status !== undefined) {
      this.status = status
    }
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null
}

function extractBusinessCode(payload: unknown): string | null {
  const record = asRecord(payload)
  if (!record) return null
  const detail = asRecord(record.detail)
  if (detail && typeof detail.code === "string") return detail.code
  return typeof record.code === "string" ? record.code : null
}

function extractBusinessMessage(payload: unknown): string | null {
  const record = asRecord(payload)
  if (!record) return null
  const detail = asRecord(record.detail)
  if (detail && typeof detail.message === "string" && detail.message) {
    return detail.message
  }
  return typeof record.message === "string" && record.message
    ? record.message
    : null
}

function mapStatus(status: number): ApiErrorCode {
  if (status === 401) return "AUTH"
  if (status === 408 || status === 429 || status >= 500) return "RETRYABLE"
  return "UNKNOWN"
}

function mapBusinessCode(code: string, status?: number): ApiErrorCode {
  const upper = code.toUpperCase()
  if (upper.includes("CONFIGURATION")) return "CONFIGURATION"
  if (upper.includes("AUTH") || upper.includes("LOGIN")) return "AUTH"
  if (upper.includes("PAGE_CHANGED") || upper.includes("PAGE_STRUCTURE")) {
    return "PAGE_CHANGED"
  }
  if (
    upper.includes("RETRYABLE") ||
    upper.includes("EXTERNAL_ADAPTER") ||
    upper.includes("TIMEOUT") ||
    upper.includes("NETWORK")
  ) {
    return "RETRYABLE"
  }
  return status !== undefined ? mapStatus(status) : "UNKNOWN"
}

export function toApiError(error: unknown, status?: number): ApiError {
  if (error instanceof ApiError) return error
  const businessCode = extractBusinessCode(error)
  const code = businessCode
    ? mapBusinessCode(businessCode, status)
    : status !== undefined
      ? mapStatus(status)
      : "RETRYABLE"
  const message = extractBusinessMessage(error) ?? ERROR_MESSAGES[code]
  return new ApiError(code, message, status)
}

export function getErrorMessage(code: ApiErrorCode): string {
  return ERROR_MESSAGES[code]
}

export function toErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : ERROR_MESSAGES.UNKNOWN
}
