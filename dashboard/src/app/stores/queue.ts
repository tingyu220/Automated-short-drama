import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet, apiPost } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface QueueItem {
  id: string
  task_id: string
  drama_name?: string | null
  state: string
  priority: number
  available_at: string
  claimed_by: string | null
  lease_until: string | null
  attempt_count: number
  next_run_at: string | null
  failure_code: string | null
  retry_safe: boolean
  created_at?: string | null
  updated_at?: string | null
}

export const useQueueStore = defineStore("queue", () => {
  const items = ref<QueueItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchQueue(state?: string) {
    loading.value = true
    error.value = null
    try {
      items.value = await apiGet<QueueItem[]>("/queue", state ? { state } : undefined)
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function pause(itemId: string, workerId: string) {
    await apiPost(`/queue/${itemId}/pause`, { worker_id: workerId })
  }

  async function resume(itemId: string, workerId: string) {
    await apiPost(`/queue/${itemId}/resume`, { worker_id: workerId })
  }

  async function cancel(itemId: string, workerId: string) {
    await apiPost(`/queue/${itemId}/cancel`, { worker_id: workerId })
  }

  async function retry(itemId: string, workerId: string) {
    await apiPost(`/queue/${itemId}/retry`, { worker_id: workerId })
  }

  return { items, loading, error, fetchQueue, pause, resume, cancel, retry }
})
