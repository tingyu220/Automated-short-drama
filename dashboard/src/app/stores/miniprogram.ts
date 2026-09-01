import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet, apiPost } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface MiniProgramTask {
  task_id: string
  drama_name: string
  operator_name: string
  operator_code: string
  organization_group: string
  organization_path: string
  drama_short_name: string | null
  album_id: string | null
  workflow_status: string
  created_at: string
  updated_at: string
}

export interface MiniProgramConfig {
  config_name: string
  mini_program: {
    app_id: string
    original_id: string
    name: string
  }
  promotion: Record<string, string>
  ocean: Record<string, unknown>
  price_tiers: Record<string, { recharge_template: string; product_library: string }>
}

export interface MiniProgramDiscoveryCapture {
  url: string
  method: string
  status: number
  endpoint_type: string
  response_body: Record<string, unknown> | unknown[]
  captured_at: string
}

export interface MiniProgramDiscovery {
  task_id: string
  capture_count: number
  endpoint_counts: Record<string, number>
  endpoint_types: string[]
  captures: MiniProgramDiscoveryCapture[]
  artifacts_path: string | null
}

export const useMiniprogramStore = defineStore("miniprogram", () => {
  const tasks = ref<MiniProgramTask[]>([])
  const currentTask = ref<MiniProgramTask | null>(null)
  const configs = ref<MiniProgramConfig[]>([])
  const discovery = ref<MiniProgramDiscovery | null>(null)

  const tasksLoading = ref(false)
  const tasksError = ref<string | null>(null)
  const configsLoading = ref(false)
  const configsError = ref<string | null>(null)
  const discoveryLoading = ref(false)
  const discoveryError = ref<string | null>(null)

  const syncing = ref(false)
  const syncResult = ref<{ created: number; updated: number; skipped: number } | null>(null)

  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchTasks(): Promise<void> {
    tasksLoading.value = true
    tasksError.value = null
    loading.value = true
    error.value = null
    try {
      tasks.value = await apiGet<MiniProgramTask[]>("/miniprogram/tasks")
    } catch (err) {
      tasksError.value = toErrorMessage(err)
      error.value = tasksError.value
      tasks.value = []
    } finally {
      tasksLoading.value = false
      loading.value = false
    }
  }

  async function fetchTask(taskId: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      currentTask.value = await apiGet<MiniProgramTask>(`/miniprogram/tasks/${taskId}`)
    } catch (err) {
      error.value = toErrorMessage(err)
      currentTask.value = null
    } finally {
      loading.value = false
    }
  }

  async function fetchConfigs(): Promise<void> {
    configsLoading.value = true
    configsError.value = null
    try {
      configs.value = await apiGet<MiniProgramConfig[]>("/miniprogram/config")
    } catch (err) {
      configsError.value = toErrorMessage(err)
      configs.value = []
    } finally {
      configsLoading.value = false
    }
  }

  async function fetchDiscovery(taskId: string): Promise<void> {
    discoveryLoading.value = true
    discoveryError.value = null
    loading.value = true
    try {
      discovery.value = await apiGet<MiniProgramDiscovery>(`/miniprogram/discovery/${taskId}`)
    } catch (err) {
      discoveryError.value = toErrorMessage(err)
      discovery.value = null
    } finally {
      discoveryLoading.value = false
      loading.value = false
    }
  }

  async function syncTasks(): Promise<boolean> {
    syncing.value = true
    try {
      const result = await apiPost<{ created: number; updated: number; skipped: number }>("/miniprogram/sync")
      syncResult.value = result
      await fetchTasks()
      return true
    } catch (err) {
      error.value = toErrorMessage(err)
      return false
    } finally {
      syncing.value = false
    }
  }

  function reset(): void {
    tasks.value = []
    currentTask.value = null
    discovery.value = null
    error.value = null
    tasksError.value = null
    configsError.value = null
    discoveryError.value = null
  }

  return {
    tasks,
    currentTask,
    configs,
    discovery,
    loading,
    error,
    tasksLoading,
    tasksError,
    configsLoading,
    configsError,
    discoveryLoading,
    discoveryError,
    syncing,
    syncResult,
    fetchTasks,
    fetchTask,
    fetchConfigs,
    fetchDiscovery,
    syncTasks,
    reset,
  }
})
