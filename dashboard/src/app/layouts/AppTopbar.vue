<script setup lang="ts">
import { onMounted } from "vue"
import { Fold } from "@element-plus/icons-vue"
import { useSystemStore } from "@/app/stores/system"

defineEmits<{ toggleSidebar: [] }>()

/** 直接使用 Pinia 全局单例，无需 prop 传递 */
const systemStore = useSystemStore()

const statusLabels = [
  { key: "environment", label: "环境" },
  { key: "workerHeartbeat", label: "Worker" },
  { key: "database", label: "数据库" }
] as const

function statusText(value: unknown): string {
  if (value === null || value === undefined) return "未知"
  return String(value)
}

onMounted(() => {
  systemStore.fetchHealth()
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
      <span v-for="s in statusLabels" :key="s.key" class="topbar__status-item">
        <span class="topbar__status-dot" :class="{ online: String(systemStore[s.key]) === 'ok' }" />
        <span class="topbar__status-label">{{ s.label }}</span>
        <span class="topbar__status-value">{{ statusText(systemStore[s.key]) }}</span>
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
.topbar__status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-status-pending); }
.topbar__status-dot.online { background: var(--color-status-success); }
.topbar__status-label { color: var(--color-text-tertiary); }
.topbar__status-value { color: var(--color-text-primary); }
</style>
