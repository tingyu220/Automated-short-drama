<script setup lang="ts">
import { ref } from "vue"
import { RouterView } from "vue-router"
import AppSidebar from "./AppSidebar.vue"
import AppTopbar from "./AppTopbar.vue"
import { useSystemStore } from "@/app/stores/system"

const systemStore = useSystemStore()
const sidebarCollapsed = ref(false)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<template>
  <div class="app-layout">
    <AppSidebar :collapsed="sidebarCollapsed" @toggle="toggleSidebar" />
    <div class="app-main" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <AppTopbar @toggle-sidebar="toggleSidebar" />
      <div v-if="!systemStore.allowFinalSubmit" class="dry-run-banner">
        <span class="dry-run-banner__icon">&#9888;</span>
        <span>Dry Run / 最终提交已关闭</span>
      </div>
      <main class="app-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout { display: flex; height: 100vh; overflow: hidden; }
.app-main { flex: 1; display: flex; flex-direction: column; height: 100vh; min-height: 0; margin-left: 224px; transition: margin-left 0.22s ease; min-width: 0; }
.app-main.sidebar-collapsed { margin-left: 64px; }
.dry-run-banner { display: flex; align-items: center; gap: 8px; padding: 8px 24px; background: var(--color-warning); color: #fff; font-size: 13px; font-weight: 500; }
.dry-run-banner__icon { font-size: 16px; }
.app-content { flex: 1; min-height: 0; padding: 24px; background: var(--color-bg-page); overflow-y: auto; }
</style>
