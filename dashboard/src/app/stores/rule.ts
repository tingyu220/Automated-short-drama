import { defineStore } from "pinia"
import { ref } from "vue"
import { apiDelete, apiGet, apiPost } from "@/shared/api/http-client"
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

export interface RuleVersionDetail extends RuleVersion {
  payload_json: Record<string, unknown>
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

export interface TemplatePriceRule {
  id: string
  key: string
  target_price: number
  min_price: number
  max_price: number
  same_distance_strategy: string
  enabled: boolean
}

export interface MaterialRuleRange {
  id: string
  key: string
  min_material_count: number
  max_material_count: number | null
  strategy: string
  base_group_count: number
  copy_count: number
  group_size_cap: number
  target_project_count: number
}

export const useRuleStore = defineStore("rule", () => {
  const ruleSets = ref<RuleSet[]>([])
  const versions = ref<RuleVersion[]>([])
  const priceRules = ref<TemplatePriceRule[]>([])
  const materialRules = ref<MaterialRuleRange[]>([])
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

  async function fetchPriceRules() {
    loading.value = true
    error.value = null
    try {
      priceRules.value = await apiGet<TemplatePriceRule[]>("/rules/price-rules")
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function fetchMaterialRules() {
    loading.value = true
    error.value = null
    try {
      materialRules.value = await apiGet<MaterialRuleRange[]>("/rules/material-rules")
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  function clearVersions() {
    versions.value = []
    error.value = null
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

  async function saveDraft(
    ruleSetId: string,
    payload: Record<string, unknown>
  ): Promise<RuleVersion | null> {
    loading.value = true
    error.value = null
    try {
      return await apiPost<RuleVersion>(`/rules/${ruleSetId}/draft`, {
        payload
      })
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

  async function deleteVersion(
    ruleSetId: string,
    versionId: string
  ): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await apiDelete(`/rules/${ruleSetId}/versions/${versionId}`)
      return true
    } catch (err) {
      error.value = toErrorMessage(err)
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchVersionDetail(
    ruleSetId: string,
    versionId: string
  ): Promise<RuleVersionDetail | null> {
    try {
      return await apiGet<RuleVersionDetail>(
        `/rules/${ruleSetId}/versions/${versionId}`
      )
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
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
    priceRules,
    materialRules,
    loading,
    error,
    fetchRules,
    fetchVersions,
    fetchPriceRules,
    fetchMaterialRules,
    clearVersions,
    validate,
    saveDraft,
    publish,
    deleteVersion,
    fetchVersionDetail,
    simulatePrice
  }
})
