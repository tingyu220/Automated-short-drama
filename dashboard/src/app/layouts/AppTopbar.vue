<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue"
import { Fold, Refresh } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { type RuntimeMode, useSystemStore } from "@/app/stores/system"

defineEmits<{ toggleSidebar: [] }>()

/** 直接使用 Pinia 全局单例，无需 prop 传递 */
const systemStore = useSystemStore()
let healthPollTimer: number | undefined

const statusLabels = [
  { key: "workerHeartbeat", label: "Worker" },
  { key: "database", label: "数据库" }
] as const

function statusText(value: unknown): string {
  if (value === null || value === undefined) return "未知"
  return String(value)
}

function workerText(): string {
  return systemStore.isWorkerOnline() ? "在线" : "离线"
}

function modeText(mode: unknown): string {
  if (mode === "REAL") return "真实"
  if (mode === "MOCK") return "模拟"
  return "未启动"
}

function executionModeText(): string {
  if (systemStore.environmentSwitching) return "切换中"
  if (systemStore.workerEnvironment !== "REAL") return "模拟演练"
  return systemStore.allowFinalSubmit ? "真实执行" : "真实链路 / 提交保护"
}

function statusValue(key: string): unknown {
  if (key === "workerHeartbeat") return systemStore.workerHeartbeat
  if (key === "database") return systemStore.database
  return null
}

async function changeEnvironment(mode: RuntimeMode) {
  if (systemStore.environment === mode || systemStore.environmentSwitching) return
  try {
    if (mode === "REAL") {
      await ElMessageBox.confirm(
        "将启动真实浏览器并使用真实番茄与投放系统。确认后，Worker 会在下一轮任务前完成切换。",
        "切换到真实环境",
        { confirmButtonText: "确认切换", cancelButtonText: "取消", type: "warning" }
      )
    }
    await systemStore.setEnvironment(mode, mode === "REAL")
    ElMessage.success("环境切换请求已提交")
  } catch (error) {
    if (error === "cancel" || error === "close") return
    ElMessage.error(error instanceof Error ? error.message : "环境切换失败")
  }
}

async function toggleOperatorMatch(val: boolean) {
  try {
    await systemStore.setOperatorMatchGroup(val)
    ElMessage.success(val ? "已切换为：同组+本人" : "已切换为：仅本人")
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "匹配范围切换失败")
  }
}

async function toggleFinalSubmit(val: boolean) {
  try {
    await systemStore.setFinalSubmit(val)
    ElMessage.success(val ? "最终提交已开启" : "最终提交已关闭")
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "最终提交开关切换失败")
  }
}

function statusDotClass(key: string): boolean {
  if (key === "workerHeartbeat") return systemStore.isWorkerOnline()
  return String(statusValue(key)) === "ok"
}

const workerRestarting = ref(false)

async function restartWorker() {
  try {
    workerRestarting.value = true
    const result = await systemStore.restartWorker()
    ElMessage.success(result.message)
    void systemStore.fetchHealth()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Worker 重启失败")
  } finally {
    workerRestarting.value = false
  }
}

function stopEnvironmentPolling() {
  if (healthPollTimer !== undefined) {
    clearInterval(healthPollTimer)
    healthPollTimer = undefined
  }
}

function startEnvironmentPolling() {
  if (healthPollTimer !== undefined) return
  healthPollTimer = window.setInterval(() => {
    void systemStore.fetchHealth()
  }, 1000)
}

watch(
  () => systemStore.environmentSwitching,
  (isSwitching) => {
    if (isSwitching) startEnvironmentPolling()
  }
)

onMounted(() => {
  void systemStore.fetchHealth()
  // Worker 心跳是运行态信息，不能只在环境切换时刷新。
  startEnvironmentPolling()
})

onUnmounted(() => {
  stopEnvironmentPolling()
})
</script>

<template>
  <header class="topbar">
    <div class="topbar__left">
      <button class="topbar__menu-btn" @click="$emit('toggleSidebar')">
        <el-icon><Fold /></el-icon>
      </button>
    </div>
    <div class="topbar__status">
      <span class="topbar__environment">
        <span class="topbar__mode-title">Worker运行模式</span>
        <el-button-group>
          <el-button
            size="small"
            :type="systemStore.environment === 'MOCK' ? 'primary' : 'default'"
            :disabled="systemStore.environmentSwitching"
            @click="changeEnvironment('MOCK')"
          >模拟模式</el-button>
          <el-button
            size="small"
            :type="systemStore.environment === 'REAL' ? 'success' : 'default'"
            :disabled="systemStore.environmentSwitching"
            @click="changeEnvironment('REAL')"
          >真实模式</el-button>
        </el-button-group>
        <span class="topbar__mode-meta">目标：{{ modeText(systemStore.environment) }}</span>
        <span class="topbar__mode-meta">生效：{{ modeText(systemStore.workerEnvironment) }}</span>
        <span class="topbar__mode-meta">{{ executionModeText() }}</span>
        <span v-if="systemStore.environmentSwitching" class="topbar__switching">
          切换中
        </span>
      </span>
      <span class="topbar__operator-match">
        <el-tooltip
          content="仅本人：只可上带自己名字的剧；同组：同组投手的剧也可上"
          placement="bottom"
        >
          <span class="topbar__mode-title">剧目匹配</span>
        </el-tooltip>
        <el-switch
          size="small"
          :model-value="systemStore.operatorMatchGroup"
          active-text="同组"
          inactive-text="仅本人"
          @change="toggleOperatorMatch"
        />
      </span>
      <span class="topbar__final-submit">
        <el-tooltip
          content="开启后允许最终计划提交到投放系统；关闭时仅搭建链接不提交"
          placement="bottom"
        >
          <span class="topbar__mode-title">最终提交</span>
        </el-tooltip>
        <el-switch
          size="small"
          :model-value="systemStore.allowFinalSubmit"
          @change="toggleFinalSubmit"
        />
      </span>
      <span v-for="s in statusLabels" :key="s.key" class="topbar__status-item">
        <span
          class="topbar__status-dot"
          :class="{ online: statusDotClass(s.key) }"
        />
        <span class="topbar__status-label">{{ s.label }}</span>
        <span class="topbar__status-value">
          {{
            s.key === "workerHeartbeat"
              ? workerText()
              : statusText(statusValue(s.key))
          }}
        </span>
        <el-button
          v-if="s.key === 'workerHeartbeat'"
          size="small"
          type="primary"
          link
          :loading="workerRestarting"
          @click="restartWorker"
        >
          <el-icon v-if="!workerRestarting"><Refresh /></el-icon>
          重启
        </el-button>
      </span>
    </div>
  </header>
</template>

<style scoped>
.topbar { display: flex; align-items: center; justify-content: space-between; height: 48px; padding: 0 20px; background: var(--color-bg-panel); border-bottom: 1px solid #e5e7eb; }
.topbar__menu-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; border-radius: 8px; background: transparent; cursor: pointer; color: var(--color-text-secondary); font-size: 18px; transition: background 0.15s ease; }
.topbar__menu-btn:hover { background: var(--color-bg-page); }
.topbar__status { display: flex; align-items: center; gap: 20px; }
.topbar__status-item { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.topbar__environment { display: flex; align-items: center; gap: 8px; }
.topbar__operator-match { display: flex; align-items: center; gap: 6px; }
.topbar__final-submit { display: flex; align-items: center; gap: 6px; }
.topbar__mode-title { color: var(--color-text-primary); font-size: 13px; font-weight: 600; white-space: nowrap; }
.topbar__mode-meta { color: var(--color-text-tertiary); font-size: 12px; white-space: nowrap; }
.topbar__environment :deep(.el-button) { min-width: 48px; border-radius: 0; }
.topbar__environment :deep(.el-button:first-child) { border-radius: 4px 0 0 4px; }
.topbar__environment :deep(.el-button:last-child) { border-radius: 0 4px 4px 0; }
.topbar__switching { color: var(--color-text-tertiary); font-size: 12px; }
.topbar__status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-status-pending); }
.topbar__status-dot.online { background: var(--color-status-success); }
.topbar__status-label { color: var(--color-text-tertiary); }
.topbar__status-value { color: var(--color-text-primary); }

@media (max-width: 720px) {
  .topbar {
    padding: 0 10px;
  }

  .topbar__status {
    gap: 8px;
  }

  .topbar__status-item {
    gap: 4px;
  }

  .topbar__environment {
    gap: 4px;
  }

  .topbar__status-label,
  .topbar__mode-title,
  .topbar__mode-meta {
    display: none;
  }

  .topbar__switching {
    display: none;
  }
}
</style>
