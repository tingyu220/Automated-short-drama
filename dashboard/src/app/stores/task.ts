import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet, apiPost } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export type TaskFilters = {
  date?: string
  platform?: string
  status?: string
  q?: string
}

export interface TaskSummary {
  id: string
  drama_name: string
  platform: string
  available_time: string
  status: string
  owner: string | null
  queue_state: string | null
  updated_at: string
}

export interface TaskDetail extends TaskSummary {
  queue_item_id: string | null
  attempt_count: number | null
  claimed_by: string | null
  lease_until: string | null
  ledger_id: string | null
}

export const useTaskStore = defineStore("task", () => {
  const tasks = ref<TaskSummary[]>([])
  const detail = ref<TaskDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

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

  async function enqueueTask(id: string) {
    loading.value = true
    error.value = null
    try {
      await apiPost(`/tasks/${id}/enqueue`)
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return { tasks, detail, loading, error, fetchTasks, fetchTask, enqueueTask }
})
