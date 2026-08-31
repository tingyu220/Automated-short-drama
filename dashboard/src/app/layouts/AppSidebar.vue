<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  Monitor,
  List,
  Switch,
  Document,
  Setting,
  Warning,
  Tickets,
  DArrowRight,
  DArrowLeft
} from "@element-plus/icons-vue"

const props = defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{ toggle: [] }>()

const route = useRoute()
const router = useRouter()

/** 一级菜单项：icon 为导入的组件引用 */
const menuItems = [
  { path: "/", name: "workspace", label: "工作台", icon: Monitor },
  { path: "/tasks", name: "tasks", label: "自动搭链接", icon: List },
  { path: "/queue", name: "queue", label: "自动化队列", icon: Switch },
  { path: "/plans", name: "plans", label: "计划管理", icon: Document },
  { path: "/rules", name: "rules", label: "规则与配置", icon: Setting },
  { path: "/exceptions", name: "exceptions", label: "异常中心", icon: Warning },
  { path: "/records", name: "records", label: "系统记录", icon: Tickets }
]

const toggleIcon = computed(() => props.collapsed ? DArrowRight : DArrowLeft)

const currentRoute = computed(() => route.name as string)

function navigate(path: string) {
  router.push(path)
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar__logo">
      <span class="sidebar__logo-text">短剧投放工作台</span>
      <span class="sidebar__logo-icon">SD</span>
    </div>
    <nav class="sidebar__nav">
      <button
        v-for="item in menuItems"
        :key="item.name"
        class="sidebar__menu-item"
        :class="{ active: currentRoute === item.name }"
        :title="item.label"
        @click="navigate(item.path)"
      >
        <el-icon class="sidebar__menu-icon"><component :is="item.icon" /></el-icon>
        <span class="sidebar__menu-label">{{ item.label }}</span>
        <span v-if="currentRoute === item.name" class="sidebar__menu-indicator" />
      </button>
    </nav>
    <button class="sidebar__toggle" @click="emit('toggle')">
      <el-icon><component :is="toggleIcon" /></el-icon>
    </button>
  </aside>
</template>

<style scoped>
.sidebar { position: fixed; top: 0; left: 0; bottom: 0; width: 224px; background: var(--color-sidebar); display: flex; flex-direction: column; transition: width 0.22s ease; z-index: 100; overflow: hidden; }
.sidebar.collapsed { width: 64px; }
.sidebar__logo { display: flex; align-items: center; justify-content: center; height: 56px; padding: 0 16px; border-bottom: 1px solid var(--color-sidebar-hover); }
.sidebar__logo-text { color: var(--color-text-inverse); font-size: 15px; font-weight: 600; white-space: nowrap; }
.sidebar__logo-icon { color: var(--color-primary); font-size: 18px; font-weight: 700; }
.sidebar:not(.collapsed) .sidebar__logo-icon { display: none; }
.sidebar.collapsed .sidebar__logo-text,
.sidebar.collapsed .sidebar__menu-label,
.sidebar.collapsed .sidebar__menu-indicator { display: none; }
.sidebar__nav { flex: 1; padding: 8px; display: flex; flex-direction: column; gap: 2px; }
.sidebar__menu-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; border: none; border-radius: 8px; background: transparent; color: var(--color-text-inverse); font-size: 14px; cursor: pointer; position: relative; transition: background 0.15s ease; text-align: left; }
.sidebar__menu-item:hover { background: var(--color-sidebar-hover); }
.sidebar__menu-item.active { background: var(--color-sidebar-active); color: #fff; }
.sidebar__menu-icon { font-size: 18px; flex-shrink: 0; }
.sidebar__menu-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sidebar__menu-indicator { position: absolute; left: 0; top: 50%; transform: translateY(-50%); width: 3px; height: 20px; background: var(--color-primary); border-radius: 0 2px 2px 0; }
.sidebar__toggle { display: flex; align-items: center; justify-content: center; height: 44px; border: none; border-top: 1px solid var(--color-sidebar-hover); background: transparent; color: var(--color-text-inverse); cursor: pointer; font-size: 16px; transition: background 0.15s ease; }
.sidebar__toggle:hover { background: var(--color-sidebar-hover); }

@media (max-width: 720px) {
  .sidebar,
  .sidebar.collapsed {
    width: 56px;
  }

  .sidebar__logo {
    padding: 0;
  }

  .sidebar__logo-text,
  .sidebar__menu-label,
  .sidebar__menu-indicator {
    display: none;
  }

  .sidebar:not(.collapsed) .sidebar__logo-icon {
    display: inline;
  }

  .sidebar__nav {
    padding: 8px 6px;
  }

  .sidebar__menu-item {
    justify-content: center;
    padding: 10px;
  }
}
</style>
