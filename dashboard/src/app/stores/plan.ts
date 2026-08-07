import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface LedgerView {
  id: string
  task_id: string
  drama_name: string
  platform: string
  sheet_row?: number | null
  album_id?: string | null
  product_id?: string | null
  final_status: string
  completed_at: string | null
  task_name?: string | null
  rule_version?: string | null
  config_version?: string | null
  external_task_id?: string | null
}

export interface PlanView {
  id: string
  taskId: string
  dramaName: string
  platform: string
  status: string
  completedAt: string | null
  feishuRow: string
  albumId: string
  productId: string
  taskName: string
  ruleVersion: string
  configVersion: string
  externalTaskId: string
}

function displayText(value: string | number | null | undefined): string {
  return value ? String(value) : "—"
}

function toPlanView(ledger: LedgerView): PlanView {
  return {
    id: ledger.id,
    taskId: ledger.task_id,
    dramaName: ledger.drama_name,
    platform: ledger.platform,
    status: ledger.final_status,
    completedAt: ledger.completed_at,
    feishuRow: displayText(ledger.sheet_row),
    albumId: displayText(ledger.album_id),
    productId: displayText(ledger.product_id),
    taskName: displayText(ledger.task_name),
    ruleVersion: displayText(ledger.rule_version),
    configVersion: displayText(ledger.config_version),
    externalTaskId: displayText(ledger.external_task_id)
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
