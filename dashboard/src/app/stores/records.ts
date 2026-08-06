import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"
import {
  formatLedgerRow,
  type LedgerView
} from "@/shared/utils/format"

export interface ExecutionEventView {
  id: string
  task_id: string
  event_type: string
  level: string
  message: string
  context_json: Record<string, unknown> | null
  occurred_at: string
}

export interface ExecutionArtifactView {
  id: string
  task_id: string
  artifact_type: string
  path: string
  size_bytes: number
  step_run_id: string | null
  checksum: string | null
  created_at: string
}

export const useRecordsStore = defineStore("records", () => {
  const ledgers = ref<LedgerView[]>([])
  const events = ref<ExecutionEventView[]>([])
  const artifacts = ref<ExecutionArtifactView[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchRecords() {
    loading.value = true
    error.value = null
    try {
      const [rawLedgers, rawEvents, rawArtifacts] = await Promise.all([
        apiGet<Array<Record<string, unknown>>>("/records/ledgers"),
        apiGet<ExecutionEventView[]>("/records/events"),
        apiGet<ExecutionArtifactView[]>("/records/artifacts")
      ])
      ledgers.value = rawLedgers.map(formatLedgerRow)
      events.value = rawEvents
      artifacts.value = rawArtifacts
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return { ledgers, events, artifacts, loading, error, fetchRecords }
})
