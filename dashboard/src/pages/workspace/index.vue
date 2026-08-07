<script setup lang="ts">
import { computed, onMounted } from "vue"
import { useRouter } from "vue-router"
import { ElButton } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import CurrentTaskPanel from "@/widgets/current-task/CurrentTaskPanel.vue"
import TaskOverviewGrid from "@/widgets/task-overview/TaskOverviewGrid.vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import { useExceptionStore } from "@/app/stores/exception"
import { useQueueStore } from "@/app/stores/queue"
import { useSessionStore } from "@/app/stores/session"
import { useSystemStore } from "@/app/stores/system"
import { useTaskStore } from "@/app/stores/task"
import {
  formatDateTime,
  formatRemainingTime,
  queueStateToStep
} from "@/entities/task/types"

const taskStore = useTaskStore()
const queueStore = useQueueStore()
const exceptionStore = useExceptionStore()
const systemStore = useSystemStore()
const sessionStore = useSessionStore()
const router = useRouter()

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

async function load() {
  await Promise.all([
    taskStore.fetchTasks({ date: today() }),
    queueStore.fetchQueue(),
    exceptionStore.fetchExceptions(),
    sessionStore.fetchSessions()
  ])
}

onMounted(load)

const current = computed(() => {
  const item = queueStore.items.find(
    (entry) => entry.state === "RUNNING" || entry.state === "CLAIMED"
  )
  if (!item) return { task: null, item: null }
  return {
    task: taskStore.tasks.find((entry) => entry.id === item.task_id) ?? null,
    item
  }
})

const upcomingTasks = computed(() =>
  [...taskStore.tasks]
    .filter((task) => Date.parse(task.available_time) >= Date.now())
    .sort(
      (a, b) =>
        Date.parse(a.available_time) - Date.parse(b.available_time)
    )
    .slice(0, 6)
)

const exceptionRows = computed(() =>
  exceptionStore.exceptions.slice(0, 5).map((item) => ({
    ...item,
    dramaName:
      taskStore.tasks.find((task) => task.id === item.task_id)?.drama_name ?? "—"
  }))
)

function exceptionColor(level: string): string {
  if (level === "ERROR" || level === "FAILED") {
    return "var(--color-status-failed)"
  }
  if (level === "WARN" || level === "MANUAL_REVIEW") {
    return "var(--color-status-warning)"
  }
  return "var(--color-status-pending)"
}

const resourceStatuses = computed(() => {
  const workerOnline = systemStore.workerHeartbeat === "ok"
  const platformStatus = (key: string, label: string) => {
    const session = sessionStore.sessions[key]
    const online = session?.status === "logged_in"
    return {
      key,
      label,
      value: online ? "已登录" : "未登录",
      online,
      running: sessionStore.running[key] === true
    }
  }
  return [
    {
      key: "worker",
      label: "Automation Worker",
      value: workerOnline ? "在线" : "离线",
      online: workerOnline,
      running: false
    },
    platformStatus("feishu", "飞书"),
    platformStatus("tomato", "番茄"),
    platformStatus("delivery", "投放系统"),
    platformStatus("ocean", "巨量")
  ]
})
</script>

<template>
  <div class="workspace">
    <header class="workspace__header">
      <div>
        <h1 class="workspace__title">工作台</h1>
        <p class="workspace__subtitle">今日自动化投放任务运行总览</p>
      </div>
      <ElButton :loading="taskStore.loading" @click="load">
        <el-icon><Refresh /></el-icon>
        刷新
      </ElButton>
    </header>

    <TaskOverviewGrid
      :tasks="taskStore.tasks"
      :queue-items="queueStore.items"
      :loading="taskStore.loading"
    />

    <div class="workspace__grid">
      <div class="workspace__main">
        <CurrentTaskPanel
          :task="current.task"
          :queue-item="current.item"
          :loading="queueStore.loading"
          :current-step="queueStateToStep(current.item?.state)"
        />
      </div>

      <aside class="workspace__side">
        <section class="workspace-panel">
          <header class="workspace-panel__header">
            <h2 class="workspace-panel__title">即将到时间</h2>
            <button
              type="button"
              class="workspace-panel__more"
              @click="router.push('/tasks')"
            >
              查看全部
            </button>
          </header>
          <EmptyState
            v-if="upcomingTasks.length === 0"
            title="暂无即将到时间任务"
            description="今天的任务时间均已完成或尚未同步"
          />
          <ul v-else class="workspace-panel__list">
            <li v-for="task in upcomingTasks" :key="task.id" class="upcoming-item">
              <div class="upcoming-item__main">
                <span class="upcoming-item__drama">{{ task.drama_name }}</span>
                <span class="upcoming-item__platform">{{ task.platform }}</span>
              </div>
              <div class="upcoming-item__meta">
                <span>{{ formatDateTime(task.available_time) }}</span>
                <span class="upcoming-item__remaining">
                  {{ formatRemainingTime(task.available_time) }}
                </span>
              </div>
            </li>
          </ul>
        </section>

        <section class="workspace-panel">
          <header class="workspace-panel__header">
            <h2 class="workspace-panel__title">异常提醒</h2>
            <span class="workspace-panel__count">
              {{ exceptionStore.exceptions.length }}
            </span>
            <button
              type="button"
              class="workspace-panel__more"
              @click="router.push('/exceptions')"
            >
              查看全部
            </button>
          </header>
          <EmptyState
            v-if="exceptionRows.length === 0"
            title="暂无异常"
            description="需要人工介入的问题会显示在这里"
          />
          <ul v-else class="workspace-panel__list">
            <li v-for="item in exceptionRows" :key="item.id" class="exception-item">
              <span
                class="exception-item__level"
                :style="{ backgroundColor: exceptionColor(item.level) }"
              />
              <div class="exception-item__main">
                <span class="exception-item__message">{{ item.message }}</span>
                <span class="exception-item__drama">
                  {{ item.dramaName }} · {{ formatDateTime(item.occurred_at) }}
                </span>
              </div>
            </li>
          </ul>
        </section>

        <section class="workspace-panel">
          <header class="workspace-panel__header">
            <h2 class="workspace-panel__title">Worker 与平台 Session</h2>
          </header>
          <ul class="resource-list">
            <li v-for="item in resourceStatuses" :key="item.label" class="resource-item">
              <StatusDot
                :color="item.online ? 'var(--color-status-success)' : 'var(--color-status-pending)'"
                :active="item.online"
              />
              <span class="resource-item__label">{{ item.label }}</span>
              <span class="resource-item__value">{{ item.value }}</span>
              <button
                v-if="!item.online && item.running && item.key !== 'worker'"
                class="resource-item__login"
                @click="sessionStore.finish(item.key)"
              >
                完成登录
              </button>
              <button
                v-else-if="!item.online && item.key !== 'worker'"
                class="resource-item__login"
                @click="sessionStore.login(item.key)"
              >
                去登录
              </button>
            </li>
          </ul>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.workspace__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.workspace__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.workspace__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}

.workspace__grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
  gap: 20px;
  align-items: start;
}

.workspace__side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workspace-panel {
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.workspace-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.workspace-panel__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.workspace-panel__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  margin-left: auto;
  margin-right: 8px;
  color: var(--color-status-warning);
  background: color-mix(in srgb, var(--color-status-warning) 12%, transparent);
  border-radius: 999px;
  font-size: var(--font-size-caption);
  font-weight: 600;
}

.workspace-panel__more {
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}

.workspace-panel__more:hover {
  text-decoration: underline;
}

.workspace-panel__list {
  display: flex;
  flex-direction: column;
  list-style: none;
}

.upcoming-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f1f3;
}

.upcoming-item:last-child,
.exception-item:last-child {
  border-bottom: none;
}

.upcoming-item__main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.upcoming-item__drama {
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upcoming-item__platform {
  flex: none;
  padding: 2px 8px;
  color: var(--color-text-secondary);
  background: var(--color-bg-panel-secondary);
  border-radius: 999px;
  font-size: var(--font-size-caption);
}

.upcoming-item__meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
  white-space: nowrap;
}

.upcoming-item__remaining {
  color: var(--color-primary);
  font-weight: 500;
}

.exception-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f1f3;
}

.exception-item__level {
  width: 8px;
  height: 8px;
  margin-top: 6px;
  flex: none;
  border-radius: 50%;
}

.exception-item__main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.exception-item__message {
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.exception-item__drama {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.resource-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  list-style: none;
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.resource-item__label {
  flex: 1;
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
}

.resource-item__value {
  color: var(--color-text-primary);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.resource-item__login {
  color: var(--color-primary);
  font-size: var(--font-size-caption);
  text-decoration: none;
  white-space: nowrap;
}

.resource-item__login:hover {
  text-decoration: underline;
}

@media (max-width: 1280px) {
  .workspace__grid {
    grid-template-columns: 1fr;
  }
}
</style>
