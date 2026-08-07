import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

interface DeliverySummary {
  counts: {
    cid: number
    ad_presets: number
    open_presets: number
    product_libraries: number
    accounts: number
  }
  extracted_at: string | null
  mapping_proposal_count: number
}

export const useDeliveryConfigStore = defineStore("deliveryConfig", () => {
  const summary = ref<DeliverySummary | null>(null)
  const cids = ref<Record<string, unknown>[]>([])
  const adPresets = ref<Record<string, unknown>[]>([])
  const openPresets = ref<Record<string, unknown>[]>([])
  const productLibraries = ref<Record<string, unknown>[]>([])
  const accounts = ref<Record<string, unknown>[]>([])
  const mappingProposal = ref<Record<string, unknown>[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadForCategory(category: string) {
    const related = ["cid", "adPreset", "openPreset", "douyin", "platform"]
    if (!related.includes(category)) {
      return
    }
    loading.value = true
    error.value = null
    try {
      const [
        summaryData,
        cidsData,
        adData,
        openData,
        libraryData,
        accountData,
        mappingData
      ] = await Promise.all([
        apiGet<DeliverySummary>("/config/delivery/summary"),
        apiGet<{ rows: Record<string, unknown>[] }>("/config/delivery/cids"),
        apiGet<{ rows: Record<string, unknown>[] }>(
          "/config/delivery/ad-presets"
        ),
        apiGet<{ rows: Record<string, unknown>[] }>(
          "/config/delivery/open-presets"
        ),
        apiGet<{ rows: Record<string, unknown>[] }>(
          "/config/delivery/product-libraries"
        ),
        apiGet<{ rows: Record<string, unknown>[] }>(
          "/config/delivery/accounts"
        ),
        apiGet<{ rows: Record<string, unknown>[] }>(
          "/config/delivery/mapping-proposal"
        )
      ])
      summary.value = summaryData
      cids.value = cidsData.rows
      adPresets.value = adData.rows
      openPresets.value = openData.rows
      productLibraries.value = libraryData.rows
      accounts.value = accountData.rows
      mappingProposal.value = mappingData.rows
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return {
    summary,
    cids,
    adPresets,
    openPresets,
    productLibraries,
    accounts,
    mappingProposal,
    loading,
    error,
    loadForCategory
  }
})
