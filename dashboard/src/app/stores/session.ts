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
  const running = ref<Record<string, boolean>>({})
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

  async function check(platform: string): Promise<PlatformSession | null> {
    loading.value = true
    error.value = null
    try {
      const status = await apiPost<PlatformSession>(
        `/sessions/${platform}/check`
      )
      sessions.value = { ...sessions.value, [platform]: status }
      if (status.status === "logged_in") {
        running.value = { ...running.value, [platform]: false }
      }
      return status
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      loading.value = false
    }
  }

  async function login(platform: string) {
    loading.value = true
    error.value = null
    try {
      const result = await apiPost<{
        platform: string
        started: boolean
        running: boolean
      }>(`/sessions/${platform}/login`)
      running.value = { ...running.value, [platform]: result.running }
      if (result.running) {
        void pollUntilLoggedIn(platform)
      }
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function finish(platform: string) {
    loading.value = true
    error.value = null
    try {
      await apiPost(`/sessions/${platform}/finish`)
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
      await check(platform)
    }
  }

  async function reset(platform: string) {
    loading.value = true
    error.value = null
    try {
      await apiPost(`/sessions/${platform}/reset`)
      running.value = { ...running.value, [platform]: false }
    } catch (err) {
      error.value = toErrorMessage(err)
    } finally {
      loading.value = false
      await check(platform)
    }
  }

  async function importFromChrome(platform: string): Promise<PlatformSession | null> {
    loading.value = true
    error.value = null
    try {
      const result = await apiPost<{
        platform: string
        cookies: number
        storage_path: string | null
        status: PlatformSession
      }>(`/sessions/${platform}/chrome-import`)
      sessions.value = {
        ...sessions.value,
        [platform]: result.status
      }
      running.value = { ...running.value, [platform]: false }
      return result.status
    } catch (err) {
      error.value = toErrorMessage(err)
      return null
    } finally {
      loading.value = false
    }
  }

  function pollUntilLoggedIn(platform: string) {
    const deadline = Date.now() + 10 * 60 * 1000
    const timer = window.setInterval(async () => {
      if (!running.value[platform] || Date.now() > deadline) {
        window.clearInterval(timer)
        running.value = { ...running.value, [platform]: false }
        return
      }
      await check(platform)
    }, 5000)
  }

  return {
    sessions,
    running,
    loading,
    error,
    fetchSessions,
    check,
    login,
    finish,
    reset,
    importFromChrome
  }
})
