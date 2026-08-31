<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"
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
  Plus,
  Refresh,
  Search,
  Upload
} from "@element-plus/icons-vue"
import ConfirmActionDialog from "@/shared/ui/ConfirmActionDialog.vue"
import DramaImportDialog from "@/features/drama-import/DramaImportDialog.vue"
import PageHeader from "@/shared/ui/PageHeader.vue"
import PaginationBar from "@/shared/ui/PaginationBar.vue"
import TaskDetailDrawer from "@/features/task-detail/TaskDetailDrawer.vue"
import ImportedDramaTable from "@/widgets/imported-drama-table/ImportedDramaTable.vue"
import TaskTable from "@/widgets/task-table/TaskTable.vue"
import { useQueueStore } from "@/app/stores/queue"
import { useSystemStore } from "@/app/stores/system"
import { useRecordsStore } from "@/app/stores/records"
import { useTaskStore } from "@/app/stores/task"
import type { DramaImportPreview } from "@/entities/drama-import/types"
import { getPlatformLabel, getStatusLabel } from "@/shared/utils/status"
import {
  toTaskView,
  type TaskAction,
  type TaskView,
  type WorkflowRunItem
} from "@/entities/task/types"

const taskStore = useTaskStore()
const queueStore = useQueueStore()
const systemStore = useSystemStore()
const recordsStore = useRecordsStore()
const route = useRoute()

const TERMINAL_QUEUE_STATES = ["COMPLETED", "CANCELLED", "DRY_RUN"]

const STATUS_OPTIONS = [
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

const END_TYPES = [
  { value: "NATIVE", label: "端原生漫剧" },
  { value: "MINIPROGRAM", label: "微信小程序" }
] as const

function beijingToday(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date())
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? ""
  return `${value("year")}-${value("month")}-${value("day")}`
}

const activeEndType = ref<string>("NATIVE")
const date = ref(beijingToday())
const searchQ = ref("")
const platform = ref("")
const status = ref("")
const exceptionFilter = ref("")
const page = ref(1)
const pageSize = ref(10)

const newDramaName = ref("")

const drawerOpen = ref(false)
const confirmVisible = ref(false)
const pendingAction = ref<{ task: TaskView; action: TaskAction } | null>(null)
const timeline = ref<WorkflowRunItem[]>([])
const importDialogOpen = ref(false)
const importPreview = ref<DramaImportPreview | null>(null)
const importOperator = ref("田雨")

const isMiniprogram = computed(() => activeEndType.value === "MINIPROGRAM")

const platformOptions = computed(() => {
  const values = Array.from(
    new Set(taskStore.tasks.map((task) => task.platform).filter(Boolean))
  )
  const fallback = ["TOMATO", "JUBIAN"]
  return (values.length > 0 ? values : fallback).map((value) => ({
    label: getPlatformLabel(value),
    value
  }))
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

const pagedTasks = computed(() =>
  filteredTasks.value.slice(
    (page.value - 1) * pageSize.value,
    page.value * pageSize.value
  )
)

async function loadAll() {
  await Promise.all([
    taskStore.fetchTasks({
      date: date.value,
      q: searchQ.value || undefined,
      platform: platform.value || undefined,
      status: status.value || undefined,
      end_type: activeEndType.value || undefined
    }),
    queueStore.fetchQueue(),
    taskStore.fetchImportedDramaRecords(date.value),
    systemStore.fetchHealth()
  ])
}

watch(activeEndType, () => {
  page.value = 1
  void loadAll()
})

async function scanNow() {
  const result = await taskStore.scanTasks()
  if (!result) {
    ElMessage.error(taskStore.error ?? "扫描失败")
    return
  }
  await loadAll()
  ElMessage.success(
    `扫描完成：新增 ${result.created_tasks} 部，更新 ${result.updated_tasks} 部，入队 ${result.enqueued} 部`
  )
}

async function createMiniprogramTask() {
  const name = newDramaName.value.trim()
  if (!name) {
    ElMessage.warning("请输入剧目名称")
    return
  }
  const result = await taskStore.createTask({
    drama_name: name,
    end_type: "MINIPROGRAM"
  })
  if (!result) {
    ElMessage.error(taskStore.error ?? "创建失败")
    return
  }
  ElMessage.success(`已创建任务「${name}」`)
  newDramaName.value = ""
  await loadAll()
}

onMounted(async () => {
  await taskStore.fetchImportOperators()
  if (!taskStore.importOperators.some((item) => item.name === importOperator.value)) {
    importOperator.value = taskStore.importOperators[0]?.name ?? ""
  }
  await loadAll()
  const taskId = route.query.task_id
  if (typeof taskId === "string" && taskId) {
    await openTaskById(taskId)
  }
})

async function openTaskById(taskId: string) {
  drawerOpen.value = true
  await taskStore.fetchTask(taskId)
  const steps = taskStore.detail?.steps ?? []
  if (steps.length > 0) {
    timeline.value = steps.map((step) => ({
      step: step.step_name,
      status: step.status,
      started_at: step.started_at,
      finished_at: step.finished_at,
      result: step.result_json ? JSON.stringify(step.result_json) : null,
      error: step.error_message ?? step.error_code ?? null
    }))
    return
  }
  void recordsStore
    .fetchTaskEvents(taskId)
    .then((events) => {
      timeline.value = events.map((event) => ({
        step: String(event.context_json?.step_name ?? event.event_type),
        status: event.level,
        started_at: event.occurred_at,
        finished_at: event.occurred_at,
        result: event.message,
        error: event.level === "ERROR" ? event.message : null
      }))
    })
    .catch(() => {
      timeline.value = []
    })
}

async function openTask(task: TaskView) {
  await openTaskById(task.id)
}

async function runQueueAction(action: TaskAction, task: TaskView) {
  try {
    if (action === "manual_enqueue") {
      await taskStore.enqueueTask(task.id)
      if (taskStore.error) {
        ElMessage.error(taskStore.error)
        return
      }
      ElMessage.success("任务已手动入队")
    } else if (action === "resume") {
      const workerId = requireActiveWorkerId()
      const item = queueStore.items.find((entry) => entry.task_id === task.id)
      if (!item) throw new Error("任务未入队")
      await queueStore.resume(item.id, workerId)
      ElMessage.success("任务已恢复")
    } else if (action === "retry") {
      const workerId = requireActiveWorkerId()
      const item = queueStore.items.find((entry) => entry.task_id === task.id)
      if (!item) throw new Error("任务未入队")
      await queueStore.retry(item.id, workerId)
      ElMessage.success("已重试当前步骤")
    } else if (action === "pause") {
      const workerId = requireActiveWorkerId()
      await taskStore.fetchTask(task.id)
      if (taskStore.detail?.queue_state && TERMINAL_QUEUE_STATES.includes(taskStore.detail.queue_state)) {
        ElMessage.info("任务已完成，无法暂停")
        await loadAll()
        return
      }
      await queueStore.fetchQueue()
      const item = queueStore.items.find((entry) => entry.task_id === task.id)
      if (!item) throw new Error("任务未入队")
      await queueStore.pause(item.id, workerId)
      ElMessage.success("任务已暂停")
    } else if (action === "cancel") {
      const workerId = requireActiveWorkerId()
      await taskStore.fetchTask(task.id)
      if (taskStore.detail?.queue_state && TERMINAL_QUEUE_STATES.includes(taskStore.detail.queue_state)) {
        ElMessage.info("任务已完成，无法取消")
        await loadAll()
        return
      }
      await queueStore.fetchQueue()
      const item = queueStore.items.find((entry) => entry.task_id === task.id)
      if (!item) throw new Error("任务未入队")
      await queueStore.cancel(item.id, workerId)
      ElMessage.success("任务已取消")
    }
    await loadAll()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "操作失败")
  }
}

function requireActiveWorkerId(): string {
  if (!systemStore.activeWorkerId) {
    throw new Error("Worker 离线，无法控制已认领任务")
  }
  return systemStore.activeWorkerId
}

async function continueTask(task: TaskView) {
  if (task.status === "MANUAL_REVIEW") {
    await openTask(task)
    ElMessage.info("请先在任务详情中确认番茄候选，再继续执行")
    return
  }
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

async function runTaskToTarget(targetStage: string) {
  const task = detailTask.value
  if (!task) return
  await enqueueTaskToStage(task, targetStage)
}

async function confirmDramaMatch(locatorKey: string) {
  const task = detailTask.value
  if (!task) return
  const result = await taskStore.confirmDramaMatch(task.id, locatorKey)
  if (!result) {
    ElMessage.error(taskStore.error ?? "确认失败")
    return
  }
  ElMessage.success("已确认候选，任务重新入队")
  await loadAll()
  await openTaskById(task.id)
}

async function enqueueTaskToStage(task: TaskView, targetStage: string) {
  await taskStore.enqueueTask(task.id, targetStage)
  if (taskStore.error) {
    ElMessage.error(taskStore.error)
    return
  }
  ElMessage.success(
    targetStage === "LINK_EXTRACTION" ? "已安排提取链接" : "已安排搭建链接"
  )
  await loadAll()
  if (drawerOpen.value && detailTask.value?.id === task.id) {
    await taskStore.fetchTask(task.id)
  }
}

async function runTaskFromList(payload: {
  task: TaskView
  targetStage: "LINK_EXTRACTION" | "LINK_READY"
}) {
  await enqueueTaskToStage(payload.task, payload.targetStage)
}

function handleCommand(payload: { task: TaskView; action: TaskAction }) {
  if (payload.action === "cancel" || payload.action === "pause") {
    pendingAction.value = payload
    confirmVisible.value = true
    return
  }
  if (payload.action === "delete") {
    pendingAction.value = payload
    confirmVisible.value = true
    return
  }
  void runQueueAction(payload.action, payload.task)
}

async function confirmDanger() {
  const payload = pendingAction.value
  if (!payload) return
  if (payload.action === "delete") {
    await taskStore.deleteTask(payload.task.id)
    if (taskStore.error) {
      ElMessage.error(taskStore.error)
      return
    }
    ElMessage.success("任务已删除")
  } else {
    await runQueueAction(payload.action, payload.task)
  }
  confirmVisible.value = false
  pendingAction.value = null
  await loadAll()
}

const confirmTitle = computed(() => {
  const action = pendingAction.value?.action
  if (action === "cancel") return "取消任务"
  if (action === "delete") return "删除任务"
  return "暂停任务"
})

const confirmContent = computed(() => {
  const payload = pendingAction.value
  if (!payload) return ""
  if (payload.action === "delete") {
    return `确定要删除任务「${payload.task.drama_name}」吗？此操作不可恢复，将删除该任务的所有关联数据（队列项、执行事件、工作流等）。`
  }
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

async function openTodayImport() {
  if (!importOperator.value) {
    ElMessage.warning("请选择人员")
    return
  }
  if (!date.value) {
    ElMessage.warning("请选择业务日期")
    return
  }
  importDialogOpen.value = true
  importPreview.value = null
  const preview = await taskStore.previewTodayImport(date.value, importOperator.value)
  if (preview) importPreview.value = preview
}

async function confirmTodayImport() {
  if (!importPreview.value) return
  const run = await taskStore.confirmImport(importPreview.value.preview_id)
  if (!run) return
  importDialogOpen.value = false
  ElMessage.success(`已导入 ${run.inserted_count} 个剧目`)
  await loadAll()
}

async function enqueueImportedTasks(taskIds: string[]) {
  for (const taskId of taskIds) {
    await taskStore.enqueueTask(taskId)
    if (taskStore.error) {
      ElMessage.error(taskStore.error)
      return
    }
  }
  ElMessage.success(`已安排搭建 ${taskIds.length} 部剧目`)
  await loadAll()
}

</script>

<template>
  <div class="tasks-page">
    <PageHeader
      title="自动搭链接"
      :subtitle="isMiniprogram
        ? '微信小程序产线：在 youxuan2 平台搭建链接'
        : '端原生漫剧产线：番茄后台提取链接 + 投放系统搭建'"
    />

    <div class="production-line-tabs">
      <button
        v-for="item in END_TYPES"
        :key="item.value"
        class="production-line-tab"
        :class="{ 'production-line-tab--active': activeEndType === item.value }"
        @click="activeEndType = item.value"
      >
        {{ item.label }}
      </button>
    </div>

    <section v-if="isMiniprogram" class="mp-quick-create" aria-label="小程序任务创建">
      <ElInput
        v-model="newDramaName"
        placeholder="输入剧目名称，直接创建小程序产线任务"
        class="mp-quick-create__input"
        @keyup.enter="createMiniprogramTask"
      />
      <ElButton type="primary" :loading="taskStore.loading" @click="createMiniprogramTask">
        <el-icon><Plus /></el-icon>
        创建任务
      </ElButton>
    </section>

    <section class="tasks-filter" aria-label="任务筛选">
      <div class="tasks-filter__criteria">
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
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
        </ElSelect>
        <ElSelect
        v-model="status"
        placeholder="任务状态"
        clearable
        @change="loadAll"
      >
        <ElOption
          v-for="item in STATUS_OPTIONS"
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
      </div>
      <div class="tasks-filter__actions">
        <ElButton :loading="taskStore.loading" @click="loadAll">
          <el-icon><Refresh /></el-icon>
          刷新
        </ElButton>
        <template v-if="!isMiniprogram">
          <ElButton :loading="taskStore.scanLoading" @click="scanNow">
            <el-icon><Search /></el-icon>
            立即扫描
          </ElButton>
          <ElSelect v-model="importOperator" class="tasks-filter__operator" aria-label="导入人员">
            <ElOption
              v-for="item in taskStore.importOperators"
              :key="item.name"
              :label="`${item.group_prefix}组 · ${item.name}`"
              :value="item.name"
            />
          </ElSelect>
          <ElButton type="primary" :loading="taskStore.importLoading" @click="openTodayImport">
            <el-icon><Download /></el-icon>
            读取今日剧目
          </ElButton>
        </template>
        <ElButton @click="enqueueFiltered">
          <el-icon><Upload /></el-icon>
          批量搭建链接
        </ElButton>
      </div>
    </section>

    <TaskTable
      :rows="pagedTasks"
      :loading="taskStore.loading"
      :error="taskStore.error"
      @view="openTask"
      @continue="continueTask"
      @run="runTaskFromList"
      @command="handleCommand"
      @retry="loadAll"
    />

    <PaginationBar
      v-model:page="page"
      v-model:page-size="pageSize"
      :total="filteredTasks.length"
    />

    <ImportedDramaTable
      v-if="!isMiniprogram"
      :rows="taskStore.importedDramaRecords"
      :loading="taskStore.importLoading"
      @enqueue="enqueueImportedTasks"
    />

    <TaskDetailDrawer
      :open="drawerOpen"
      :task="detailTask"
      :timeline="timeline"
      @run="runTaskToTarget"
      @confirm-drama-match="confirmDramaMatch"
      @update:open="drawerOpen = $event"
    />

    <DramaImportDialog
      v-model="importDialogOpen"
      :preview="importPreview"
      :loading="taskStore.importLoading"
      :error="taskStore.importError"
      @confirm="confirmTodayImport"
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

.production-line-tabs {
  display: flex;
  gap: 0;
  border-bottom: 2px solid #e5e7eb;
}

.production-line-tab {
  padding: 10px 24px;
  font-size: 15px;
  font-weight: 500;
  color: var(--color-text-tertiary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}

.production-line-tab:hover {
  color: var(--color-text-primary);
}

.production-line-tab--active {
  color: #4f6ef7;
  border-bottom-color: #4f6ef7;
}

.mp-quick-create {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.mp-quick-create__input {
  flex: 1;
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
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.tasks-filter__criteria {
  display: grid;
  grid-template-columns: minmax(180px, 220px) minmax(180px, 1fr) repeat(3, minmax(120px, 150px));
  min-width: 0;
  gap: 10px;
}

.tasks-filter__search {
  width: 100%;
}

.tasks-filter :deep(.el-select) {
  width: 100%;
}

.tasks-filter__actions {
  display: grid;
  grid-template-columns: auto auto minmax(145px, 170px) auto auto;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

@media (max-width: 1650px) {
  .tasks-filter {
    grid-template-columns: 1fr;
  }

  .tasks-filter__criteria {
    grid-template-columns: repeat(5, minmax(120px, 1fr));
  }

  .tasks-filter__actions {
    justify-content: start;
  }
}

@media (max-width: 720px) {
  .tasks-filter {
    align-items: stretch;
  }

  .tasks-filter__criteria {
    grid-template-columns: 1fr;
  }

  .tasks-filter :deep(.el-date-editor),
  .tasks-filter__search,
  .tasks-filter :deep(.el-select) {
    width: 100%;
  }

  .tasks-filter__actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
  }

  .tasks-filter__criteria {
    width: 100%;
  }

  .tasks-filter__actions :deep(.el-button),
  .tasks-filter__actions :deep(.el-select) {
    width: 100%;
    margin: 0;
  }
}
</style>
