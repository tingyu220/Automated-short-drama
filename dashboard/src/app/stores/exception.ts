import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface ExceptionItem {
  id: string
  task_id: string
  level: string
  message: string
  occurred_at: string
}

export const useExceptionStore = defineStore("exception", () => {
  const exceptions = ref<ExceptionItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchExceptions() {
    loading.value = true
    error.value = null
    try {
      exceptions.value = await apiGet<ExceptionItem[]>("/exceptions")
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return { exceptions, loading, error, fetchExceptions }
})
