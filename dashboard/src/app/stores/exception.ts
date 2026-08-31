import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"
import {
  classifyException,
  getRiskMeta,
  type ExceptionCategoryKey,
  type RiskLevel
} from "@/shared/utils/format"

export interface ExceptionItem {
  id: string
  task_id: string
  drama_name?: string | null
  platform?: string | null
  step?: string | null
  error_type?: string | null
  failure_code?: string | null
  failure_details?: Record<string, unknown> | null
  retry_safe?: boolean | null
  message: string
  occurred_at: string
  level: string
  retry_count?: number | null
  category: ExceptionCategoryKey
  category_label: string
  risk: RiskLevel
  risk_label: string
  risk_color: string
  screenshots?: string[] | null
  page_url?: string | null
  related_config?: Record<string, string | number | boolean> | null
  suggested_steps?: string[] | null
  stack_trace?: string | null
}

type RawException = Omit<ExceptionItem, "category" | "category_label" | "risk" | "risk_label" | "risk_color">

function toExceptionItem(raw: RawException): ExceptionItem {
  const category = classifyException(raw.message, raw.error_type)
  const risk = getRiskMeta(
    raw.level === "MANUAL_REVIEW" ? "medium" : category.risk
  )
  return {
    ...raw,
    category: category.key,
    category_label: category.label,
    risk: category.risk,
    risk_label: risk.label,
    risk_color: risk.color,
    suggested_steps: raw.suggested_steps?.length
      ? raw.suggested_steps
      : category.suggested_steps,
    screenshots: raw.screenshots ?? null
  }
}

export const useExceptionStore = defineStore("exception", () => {
  const exceptions = ref<ExceptionItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchExceptions() {
    loading.value = true
    error.value = null
    try {
      const raw = await apiGet<RawException[]>("/exceptions")
      exceptions.value = raw.map(toExceptionItem)
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return { exceptions, loading, error, fetchExceptions }
})
