import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface AccountOverview {
  sync_status: string
  last_synced_at: string | null
  accounts: Array<Record<string, unknown>>
}

export const useAccountStore = defineStore("account", () => {
  const overview = ref<AccountOverview | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchOverview() {
    loading.value = true
    error.value = null
    try {
      overview.value = await apiGet<AccountOverview>("/accounts/overview")
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return { overview, loading, error, fetchOverview }
})
