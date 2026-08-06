<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import {
  ElButton,
  ElDatePicker,
  ElInput,
  ElMessage,
  ElOption,
  ElSelect
} from "element-plus"
import {
  Download,
  Refresh,
  Search,
  Upload
} from "@element-plus/icons-vue"
import ConfirmActionDialog from "@/shared/ui/ConfirmActionDialog.vue"
import TaskDetailDrawer from "@/features/task-detail/TaskDetailDrawer.vue"
import TaskTable from "@/widgets/task-table/TaskTable.vue"
import { useQueueStore } from "@/app/stores/queue"
import { useTaskStore } from "@/app/stores/task"
import { getStatusLabel } from "@/shared/utils/status"
import {
  toTaskView,
  type TaskAction,
  type TaskView
} from "@/entities/task/types"

const taskStore = useTaskStore()
const queueStore = useQueueStore()

const WORKER_ID = "ui-worker"
const TERMINAL_QUEUE_STATES = ["COMPLETED", "CANCELLED"]

const STAGE_OPTIONS = [
  "WAITING_TIME",
  "READY",
  "QUEUED",
  "CLAIMED",
  "RUNNING",
  "RETRY_WAIT",
  "PAUSED",
  "MANUAL_REVIEW",
  "COMPLETED",
  "FAILED",
  "CANCELLED"
]

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const date = ref(today())
const searchQ = ref("")
const platform = ref("")
const status = ref("")
const stage = ref("")
const exceptionFilter = ref("")

const drawerOpen = ref(false)
const confirmVisible = ref(false)
const pendingAction = ref<{ task: TaskView; action: TaskAction } | null>(null)

const platformOptions = computed(() => {
  const values = Array.from(
    new Set(taskStore.tasks.map((task) => task.platform).filter(Boolean))
  )
  return values.length > 0 ? values : ["番茄", "剧变"]
})

const detailTask = computed<TaskView | null>(() =>
  taskStore.detail ? toTaskView(taskStore.detail) : null
)

const filteredTasks = computed(() => {
  const q = searchQ.value.trim().toLowerCase()
  return taskStore.tasks
    .map((task) => toTaskView(task))
    .filter((task) => {
      if (platform.value && task.platform !== platform.value) return false
      if (status.value && task.status !== status.value) return false
      if (stage.value && (task.queue_state ?? task.status) !== stage.value) {
        return false
      }
      if (
        exceptionFilter.value === "has" &&
        !["MANUAL_REVIEW", "FAILED"].includes(task.status)
      ) {
        return false
      }
      if (
        exceptionFilter.value === "none" &&
        ["MANUAL_REVIEW", "FAILED"].includes(task.status)
      ) {
        return false
      }
      if (q && !task.drama_name.toLowerCase().includes(q)) return false
      return true
    })
})

async function loadAll() {
  await Promise.all([
    taskStore.fetchTasks({
      date: date.value,
      q: searchQ.value || undefined,
      platform: platform.value || undefined,
      status: status.value || undefined
    }),
    queueStore.fetchQueue()
  ])
}

onMounted(loadAll)

function openTask(task: TaskView) {
  drawerOpen.value = true
  void taskStore.fetchTask(task.id)
}

async function runQueueAction(action: TaskAction, task: TaskView) {
  const item = queueStore.items.find((entry) => entry.task_id === task.id)
  try {
    if (action === "manual_enqueue") {
      await taskStore.enqueueTask(task.id)
      if (taskStore.error) {
        ElMessage.error(taskStore.error)
        return
      }
      ElMessage.success("任务已手动入队")
    } else if (action === "resume") {
      if (!item) throw new Error("任务未入队")
      await queueStore.resume(item.id, WORKER_ID)
      ElMessage.success("任务已恢复")
    } else if (action === "retry") {
      if (!item) throw new Error("任务未入队")
      await queueStore.retry(item.id, WORKER_ID)
      ElMessage.success("已重试当前步骤")
    } else if (action === "pause") {
      if (!item) throw new Error("任务未入队")
      await queueStore.pause(item.id, WORKER_ID)
      ElMessage.success("任务已暂停")
    } else if (action === "cancel") {
      if (!item) throw new Error("任务未入队")
      await queueStore.cancel(item.id, WORKER_ID)
      ElMessage.success("任务已取消")
    }
    await loadAll()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "操作失败")
  }
}

async function continueTask(task: TaskView) {
  if (!task.queue_state || TERMINAL_QUEUE_STATES.includes(task.queue_state)) {
    await runQueueAction("manual_enqueue", task)
  } else if (
    task.queue_state === "PAUSED" ||
    task.queue_state === "RETRY_WAIT"
  ) {
    await runQueueAction("resume", task)
  } else {
    ElMessage.info("任务正在执行中")
  }
}

function handleCommand(payload: { task: TaskView; action: TaskAction }) {
  if (payload.action === "cancel" || payload.action === "pause") {
    pendingAction.value = payload
    confirmVisible.value = true
    return
  }
  void runQueueAction(payload.action, payload.task)
}

async function confirmDanger() {
  const payload = pendingAction.value
  if (!payload) return
  await runQueueAction(payload.action, payload.task)
  confirmVisible.value = false
  pendingAction.value = null
}

const confirmTitle = computed(() =>
  pendingAction.value?.action === "cancel" ? "取消任务" : "暂停任务"
)

const confirmContent = computed(() => {
  const payload = pendingAction.value
  if (!payload) return ""
  const verb = payload.action === "cancel" ? "取消" : "暂停"
  return `确定要${verb}任务「${payload.task.drama_name}」吗？此操作会影响后续自动化流程。`
})

async function enqueueFiltered() {
  const candidates = filteredTasks.value.filter(
    (task) =>
      !task.queue_state || TERMINAL_QUEUE_STATES.includes(task.queue_state)
  )
  if (candidates.length === 0) {
    ElMessage.info("当前筛选结果没有可入队任务")
    return
  }
  for (const task of candidates) {
    await taskStore.enqueueTask(task.id)
  }
  if (taskStore.error) {
    ElMessage.error(taskStore.error)
    return
  }
  ElMessage.success(`已入队 ${candidates.length} 个任务`)
  await loadAll()
}

function syncFeishu() {
  ElMessage.info("飞书同步将在后续阶段接入")
}

function exportTasks() {
  ElMessage.info("导出功能将在后续阶段接入")
}
</script>

<template>
  <div class="tasks-page">
    <header class="tasks-page__header">
      <div>
        <h1 class="tasks-page__title">今日任务</h1>
        <p class="tasks-page__subtitle">当天从飞书同步的剧目投放任务</p>
      </div>
    </header>

    <section class="tasks-filter" aria-label="任务筛选">
      <ElDatePicker
        v-model="date"
        type="date"
        value-format="YYYY-MM-DD"
        placeholder="选择日期"
        :clearable="false"
        @change="loadAll"
      />
      <ElInput
        v-model="searchQ"
        class="tasks-filter__search"
        placeholder="搜索剧名"
        clearable
        @keyup.enter="loadAll"
        @clear="loadAll"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </ElInput>
      <ElSelect
        v-model="platform"
        placeholder="平台"
        clearable
        @change="loadAll"
      >
        <ElOption
          v-for="item in platformOptions"
          :key="item"
          :label="item"
          :value="item"
        />
      </ElSelect>
      <ElSelect
        v-model="status"
        placeholder="任务状态"
        clearable
        @change="loadAll"
      >
        <ElOption
          v-for="item in STAGE_OPTIONS"
          :key="item"
          :label="getStatusLabel(item)"
          :value="item"
        />
      </ElSelect>
      <ElSelect
        v-model="stage"
        placeholder="当前阶段"
        clearable
        @change="loadAll"
      >
        <ElOption
          v-for="item in STAGE_OPTIONS"
          :key="item"
          :label="getStatusLabel(item)"
          :value="item"
        />
      </ElSelect>
      <ElSelect
        v-model="exceptionFilter"
        placeholder="异常状态"
        clearable
      >
        <ElOption label="有异常" value="has" />
        <ElOption label="无异常" value="none" />
      </ElSelect>
      <div class="tasks-filter__actions">
        <ElButton @click="syncFeishu">
          <el-icon><Refresh /></el-icon>
          同步飞书
        </ElButton>
        <ElButton :loading="taskStore.loading" @click="loadAll">
          <el-icon><Refresh /></el-icon>
          刷新
        </ElButton>
        <ElButton @click="enqueueFiltered">
          <el-icon><Upload /></el-icon>
          手动入队
        </ElButton>
        <ElButton @click="exportTasks">
          <el-icon><Download /></el-icon>
          导出
        </ElButton>
      </div>
    </section>

    <TaskTable
      :rows="filteredTasks"
      :loading="taskStore.loading"
      :error="taskStore.error"
      @view="openTask"
      @continue="continueTask"
      @command="handleCommand"
      @retry="loadAll"
    />

    <TaskDetailDrawer
      :open="drawerOpen"
      :task="detailTask"
      @update:open="drawerOpen = $event"
    />

    <ConfirmActionDialog
      v-model="confirmVisible"
      :title="confirmTitle"
      :content="confirmContent"
      :confirm-text="pendingAction?.action === 'cancel' ? '取消任务' : '暂停任务'"
      @confirm="confirmDanger"
    />
  </div>
</template>

<style scoped>
.tasks-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tasks-page__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.tasks-page__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}

.tasks-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.tasks-filter__search {
  width: 200px;
}

.tasks-filter :deep(.el-select) {
  width: 140px;
}

.tasks-filter__actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

@media (max-width: 1200px) {
  .tasks-filter__actions {
    margin-left: 0;
  }
}
</style>
