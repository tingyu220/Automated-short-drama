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
  task_name?: string | null
  plan_type?: string | null
  account_count?: number | null
  cid_count?: number | null
  material_count?: number | null
  material_group_count?: number | null
  expected_project_count?: number | null
  rule_version?: string | null
  validation_status?: string | null
  submit_status?: string | null
  external_task_id?: string | null
  created_at?: string | null
}

export interface PlanView {
  id: string
  taskId: string
  dramaName: string
  platform: string
  status: string
  completedAt: string | null
  taskName: string
  planType: string
  accountCount: string
  cidCount: string
  materialCount: string
  materialGroupCount: string
  expectedProjectCount: string
  ruleVersion: string
  validationStatus: string
  submitStatus: string
  externalTaskId: string
  createdAt: string
}

function displayText(value: string | null | undefined): string {
  return value ? String(value) : "—"
}

function displayCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(value)
}

function toPlanView(ledger: LedgerView): PlanView {
  return {
    id: ledger.id,
    taskId: ledger.task_id,
    dramaName: ledger.drama_name,
    platform: ledger.platform,
    status: ledger.final_status,
    completedAt: ledger.completed_at,
    taskName: displayText(ledger.task_name),
    planType: displayText(ledger.plan_type),
    accountCount: displayCount(ledger.account_count),
    cidCount: displayCount(ledger.cid_count),
    materialCount: displayCount(ledger.material_count),
    materialGroupCount: displayCount(ledger.material_group_count),
    expectedProjectCount: displayCount(ledger.expected_project_count),
    ruleVersion: displayText(ledger.rule_version),
    validationStatus: displayText(ledger.validation_status),
    submitStatus: displayText(ledger.submit_status),
    externalTaskId: displayText(ledger.external_task_id),
    createdAt: displayText(ledger.created_at)
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
