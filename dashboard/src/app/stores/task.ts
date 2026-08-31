import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet, apiPost } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"
import type { LinkStageRun } from "@/entities/task/types"
import type {
  DramaImportPreview,
  DramaImportRun,
  DramaImportOperator,
  ImportedDramaRecord
} from "@/entities/drama-import/types"

export type TaskFilters = {
  date?: string
  platform?: string
  status?: string
  q?: string
  end_type?: string
}

export interface TaskSummary {
  id: string
  drama_name: string
  platform: string
  end_type: string
  available_time: string
  status: string
  owner: string | null
  queue_state: string | null
  current_stage?: string | null
  target_stage?: string | null
  updated_at: string
}

export interface TaskDetail extends TaskSummary {
  queue_item_id: string | null
  attempt_count: number | null
  claimed_by: string | null
  lease_until: string | null
  ledger_id: string | null
  link_set?: Record<string, string>
  delivery_drama_id?: string | null
  promotion_configs?: Record<string, string>
  steps?: LinkStageRun[]
  drama_match_candidates?: Array<Record<string, unknown>>
  confirmed_drama_match?: Record<string, string> | null
}

export interface TaskScanResult {
  day: string
  created_tasks: number
  updated_tasks: number
  enqueued: number
  skipped: number
  mode: string
}

export const useTaskStore = defineStore("task", () => {
  const tasks = ref<TaskSummary[]>([])
  const detail = ref<TaskDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const importLoading = ref(false)
  const importError = ref<string | null>(null)
  const importOperators = ref<DramaImportOperator[]>([])
  const importedDramaRecords = ref<ImportedDramaRecord[]>([])
  const scanLoading = ref(false)

  async function fetchTasks(filters: TaskFilters = {}) {
    loading.value = true
    error.value = null
    try {
      tasks.value = await apiGet<TaskSummary[]>("/tasks", filters)
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function fetchTask(id: string) {
    loading.value = true
    error.value = null
    try {
      detail.value = await apiGet<TaskDetail>(`/tasks/${id}`)
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function enqueueTask(id: string, targetStage = "LINK_READY") {
    loading.value = true
    error.value = null
    try {
      await apiPost(`/tasks/${id}/enqueue`, { target_stage: targetStage })
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function confirmDramaMatch(id: string, locatorKey: string) {
    loading.value = true
    error.value = null
    try {
      return await apiPost(`/tasks/${id}/confirm-drama-match`, {
        locator_key: locatorKey
      })
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      loading.value = false
    }
  }

  async function scanTasks() {
    scanLoading.value = true
    error.value = null
    try {
      return await apiPost<TaskScanResult>("/tasks/scan")
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      scanLoading.value = false
    }
  }

  async function fetchImportOperators() {
    try {
      importOperators.value = await apiGet<DramaImportOperator[]>("/drama-import/operators")
    } catch (err) {
      importError.value = toErrorMessage(err)
    }
  }

  async function previewTodayImport(businessDate: string, operatorName: string) {
    importLoading.value = true
    importError.value = null
    try {
      return await apiPost<DramaImportPreview>("/drama-import/preview", {
        business_date: businessDate,
        operator_name: operatorName
      })
    } catch (err) {
      importError.value = toErrorMessage(err)
      return null
    } finally {
      importLoading.value = false
    }
  }

  async function confirmImport(previewId: string) {
    importLoading.value = true
    importError.value = null
    try {
      return await apiPost<DramaImportRun>("/drama-import/confirm", {
        preview_id: previewId
      })
    } catch (err) {
      importError.value = toErrorMessage(err)
      return null
    } finally {
      importLoading.value = false
    }
  }

  async function fetchImportRun(runId: string) {
    importLoading.value = true
    importError.value = null
    try {
      return await apiGet<DramaImportRun>(`/drama-import/runs/${runId}`)
    } catch (err) {
      importError.value = toErrorMessage(err)
      return null
    } finally {
      importLoading.value = false
    }
  }

  async function fetchImportedDramaRecords(businessDate: string) {
    importLoading.value = true
    importError.value = null
    try {
      importedDramaRecords.value = await apiGet<ImportedDramaRecord[]>(
        "/drama-import/records",
        { business_date: businessDate }
      )
    } catch (err) {
      importError.value = toErrorMessage(err)
    } finally {
      importLoading.value = false
    }
  }

  async function deleteTask(id: string) {
    loading.value = true
    error.value = null
    try {
      await fetch(`/api/tasks/${id}`, { method: "DELETE" })
      if (detail.value?.id === id) {
        detail.value = null
      }
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function createTask(data: {
    drama_name: string
    end_type?: string
    platform?: string
  }) {
    loading.value = true
    error.value = null
    try {
      return await apiPost<TaskSummary>("/tasks", {
        drama_name: data.drama_name,
        end_type: data.end_type ?? "NATIVE",
        platform: data.platform ?? "TOMATO"
      })
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    tasks,
    detail,
    loading,
    error,
    importLoading,
    importError,
    importOperators,
    importedDramaRecords,
    scanLoading,
    fetchTasks,
    fetchTask,
    enqueueTask,
    confirmDramaMatch,
    scanTasks,
    fetchImportOperators,
    previewTodayImport,
    confirmImport,
    fetchImportRun,
    fetchImportedDramaRecords,
    deleteTask,
    createTask
  }
})
