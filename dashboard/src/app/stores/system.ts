import { defineStore } from "pinia"
import { ref } from "vue"

export const useSystemStore = defineStore("system", () => {
  const environment = ref<string>("development")
  const allowFinalSubmit = ref<boolean>(false)
  const workerHeartbeat = ref<string | null>(null)
  const database = ref<string | null>(null)
  const config = ref<Record<string, unknown> | null>(null)

  async function fetchHealth() {
    try {
      const res = await fetch("/healthz")
      if (!res.ok) throw new Error("HTTP " + res.status)
      const json = await res.json()
      environment.value = json.environment ?? "unknown"
      allowFinalSubmit.value = json.allow_final_submit ?? false
      workerHeartbeat.value = json.worker_heartbeat ?? null
      database.value = json.database ?? null
      config.value = json.config ?? null
    } catch {
      // silent
    }
  }

  return { environment, allowFinalSubmit, workerHeartbeat, database, config, fetchHealth }
})
