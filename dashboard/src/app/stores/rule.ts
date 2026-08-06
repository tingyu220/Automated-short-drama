import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet, apiPost } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface RuleSet {
  id: string
  key: string
  name: string
  category: string
  status: string
  updated_at: string
}

export interface RuleVersion {
  id: string
  version: string
  status: string
  published_at: string | null
}

export interface SimulationOutput {
  candidate: number
  matched_rule_key: string | null
  target_price: number | null
  distance: number | null
  selection_reason: string
}

export interface SimulationResult {
  inputs: number[]
  outputs: SimulationOutput[]
}

export const useRuleStore = defineStore("rule", () => {
  const ruleSets = ref<RuleSet[]>([])
  const versions = ref<RuleVersion[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchRules() {
    loading.value = true
    error.value = null
    try {
      ruleSets.value = await apiGet<RuleSet[]>("/rules")
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function fetchVersions(ruleSetId: string) {
    loading.value = true
    error.value = null
    try {
      versions.value = await apiGet<RuleVersion[]>(
        `/rules/${ruleSetId}/versions`
      )
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function validate(ruleSetId: string): Promise<RuleVersion | null> {
    loading.value = true
    error.value = null
    try {
      return await apiPost<RuleVersion>(`/rules/${ruleSetId}/validate`)
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      loading.value = false
    }
  }

  async function publish(ruleSetId: string): Promise<RuleVersion | null> {
    loading.value = true
    error.value = null
    try {
      return await apiPost<RuleVersion>(`/rules/${ruleSetId}/publish`)
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      loading.value = false
    }
  }

  async function simulatePrice(
    candidates: number[]
  ): Promise<SimulationResult | null> {
    loading.value = true
    error.value = null
    try {
      return await apiPost<SimulationResult>("/rules/simulate-price", {
        candidates
      })
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    ruleSets,
    versions,
    loading,
    error,
    fetchRules,
    fetchVersions,
    validate,
    publish,
    simulatePrice
  }
})
