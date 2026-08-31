import { defineStore } from "pinia"
import { ref } from "vue"

export type RuntimeMode = "MOCK" | "REAL"

export const useSystemStore = defineStore("system", () => {
  const environment = ref<string>("MOCK")
  const workerEnvironment = ref<RuntimeMode | null>(null)
  const environmentSwitching = ref(false)
  const operatorMatchGroup = ref(false)
  const allowFinalSubmit = ref<boolean>(false)
  const workerHeartbeat = ref<string | boolean | null>(null)
  const activeWorkerId = ref<string | null>(null)
  const database = ref<string | null>(null)
  const config = ref<Record<string, unknown> | null>(null)

  async function fetchHealth() {
    try {
      const res = await fetch("/healthz")
      if (!res.ok) throw new Error("HTTP " + res.status)
      const json = await res.json()
      environment.value = json.environment ?? "MOCK"
      workerEnvironment.value = json.worker_environment ?? null
      environmentSwitching.value = json.environment_switching ?? false
      operatorMatchGroup.value = json.operator_match_group ?? false
      allowFinalSubmit.value = json.allow_final_submit ?? false
      workerHeartbeat.value = json.worker_heartbeat ?? null
      activeWorkerId.value = json.active_worker_id ?? null
      database.value = json.database ?? null
      config.value = json.config ?? null
    } catch {
      // silent
    }
  }

  async function setEnvironment(
    mode: RuntimeMode,
    confirmReal = false
  ): Promise<void> {
    const res = await fetch("/api/runtime/environment", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, confirm_real: confirmReal })
    })
    const json = await res.json()
    if (!res.ok) {
      throw new Error(json.detail ?? "环境切换失败")
    }
    environment.value = json.desired_mode
    workerEnvironment.value = json.worker_mode
    environmentSwitching.value = json.switching
  }

  async function setOperatorMatchGroup(matchGroup: boolean): Promise<void> {
    const res = await fetch("/api/runtime/operator-match", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_group: matchGroup })
    })
    const json = await res.json()
    if (!res.ok) {
      throw new Error(json.detail ?? "匹配范围切换失败")
    }
    operatorMatchGroup.value = json.operator_match_group
  }

  async function setFinalSubmit(allow: boolean): Promise<void> {
    const res = await fetch("/api/runtime/final-submit", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ allow })
    })
    const json = await res.json()
    if (!res.ok) {
      throw new Error(json.detail ?? "最终提交开关切换失败")
    }
    allowFinalSubmit.value = json.allow_final_submit
  }

  function isWorkerOnline(): boolean {
    return (
      workerHeartbeat.value === true ||
      workerHeartbeat.value === "ok" ||
      workerHeartbeat.value === "online" ||
      workerHeartbeat.value === "1"
    )
  }

  async function restartWorker(): Promise<{ killed: number; new_pid: number | null; message: string }> {
    const res = await fetch("/api/worker/restart", { method: "POST" })
    const json = await res.json()
    if (!res.ok) {
      throw new Error(json.detail ?? "Worker 重启失败")
    }
    return json
  }

  return {
    environment,
    workerEnvironment,
    environmentSwitching,
    operatorMatchGroup,
    allowFinalSubmit,
    workerHeartbeat,
    activeWorkerId,
    database,
    config,
    fetchHealth,
    setEnvironment,
    setOperatorMatchGroup,
    setFinalSubmit,
    isWorkerOnline,
    restartWorker
  }
})
