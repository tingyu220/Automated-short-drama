import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface LedgerView {
  id: string
  task_id: string
  drama_name: string
  platform: string
  final_status: string
  completed_at: string | null
}

export interface PlanView {
  id: string
  taskId: string
  dramaName: string
  platform: string
  status: string
  completedAt: string | null
}

function toPlanView(ledger: LedgerView): PlanView {
  return {
    id: ledger.id,
    taskId: ledger.task_id,
    dramaName: ledger.drama_name,
    platform: ledger.platform,
    status: ledger.final_status,
    completedAt: ledger.completed_at
  }
}

export const usePlanStore = defineStore("plan", () => {
  const plans = ref<PlanView[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchPlans() {
    loading.value = true
    error.value = null
    try {
      const ledgers = await apiGet<LedgerView[]>("/records/ledgers")
      plans.value = ledgers.map(toPlanView)
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return { plans, loading, error, fetchPlans }
})
