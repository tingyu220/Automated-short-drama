import { defineStore } from "pinia"
import { ref } from "vue"
import { apiGet, apiPost } from "@/shared/api/http-client"
import { toErrorMessage } from "@/shared/api/error-handler"

export interface PlatformSession {
  platform: string
  status: string
  login_url: string
  message: string
  expires_at: string | null
  storage_path: string | null
}

export const useSessionStore = defineStore("session", () => {
  const sessions = ref<Record<string, PlatformSession>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchSessions() {
    loading.value = true
    error.value = null
    try {
      sessions.value = await apiGet<Record<string, PlatformSession>>(
        "/sessions"
      )
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function check(platform: string) {
    loading.value = true
    error.value = null
    try {
      const status = await apiPost<PlatformSession>(
        `/sessions/${platform}/check`
      )
      sessions.value = { ...sessions.value, [platform]: status }
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return { sessions, loading, error, fetchSessions, check }
})
