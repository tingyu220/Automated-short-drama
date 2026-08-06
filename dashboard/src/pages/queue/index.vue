<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ElButton, ElMessage } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import ConfirmActionDialog from "@/shared/ui/ConfirmActionDialog.vue"
import QueueMonitor, {
  type QueueAction,
  type QueueWorkerStatus
} from "@/widgets/queue-monitor/QueueMonitor.vue"
import { useQueueStore, type QueueItem } from "@/app/stores/queue"
import { useSystemStore } from "@/app/stores/system"
import { useTaskStore } from "@/app/stores/task"
import {
  formatDateTime,
  formatDuration,
  queueStateToStep,
  WORKFLOW_STEPS
} from "@/entities/task/types"

const queueStore = useQueueStore()
const taskStore = useTaskStore()
const systemStore = useSystemStore()

const WORKER_ID = "ui-worker"

const confirmVisible = ref(false)
const pendingAction = ref<{ item: QueueItem; action: QueueAction } | null>(null)

const RISK_TEXT: Record<
  "release_lock" | "force_stop" | "requeue" | "cancel",
  string
> = {
  release_lock:
    "释放 Worker 锁后，当前执行进度可能丢失，任务将由恢复流程重新领取。",
  force_stop:
    "强制停止会中断当前执行，未完成的写操作可能产生部分写入或结果不确定，需要人工核对。",
  requeue:
    "重新入队会把任务放回排队中并重置重试次数，正在执行的步骤不会继续。",
  cancel: "取消任务会终止后续自动化流程，且无法自动恢复。"
}

const ACTION_LABEL: Record<QueueAction, string> = {
  release_lock: "释放锁",
  force_stop: "强制停止",
  requeue: "重新入队",
  cancel: "取消任务",
  pause: "暂停",
  resume: "恢复"
}

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

async function load() {
  await Promise.all([
    queueStore.fetchQueue(),
    taskStore.fetchTasks({ date: today() }),
    systemStore.fetchHealth()
  ])
}

onMounted(load)

const runningItem = computed(
  () =>
    queueStore.items.find(
      (item) => item.state === "RUNNING" || item.state === "CLAIMED"
    ) ?? null
)

const workerStatus = computed<QueueWorkerStatus>(() => {
  const heartbeat = systemStore.workerHeartbeat
  const online =
    heartbeat === true ||
    heartbeat === "ok" ||
    heartbeat === "online" ||
    heartbeat === "1"
  const item = runningItem.value
  const task = item
    ? taskStore.tasks.find((entry) => entry.id === item.task_id)
    : undefined
  const stepKey = queueStateToStep(item?.state)
  const step =
    WORKFLOW_STEPS.find((entry) => entry.key === stepKey)?.label ?? "—"
  return {
    online,
    heartbeatText: online ? "正常" : "离线",
    currentTask: task?.drama_name ?? "—",
    leaseUntil: item?.lease_until
      ? formatDateTime(item.lease_until)
      : "—",
    platform: task?.platform ?? "—",
    step,
    runtime: item
      ? formatDuration(
          item.updated_at ?? item.created_at ?? item.available_at
        )
      : "—"
  }
})

function handleAction(payload: { item: QueueItem; action: QueueAction }) {
  if (payload.action === "pause" || payload.action === "resume") {
    void runAction(payload)
    return
  }
  pendingAction.value = payload
  confirmVisible.value = true
}

async function confirmDanger() {
  const payload = pendingAction.value
  if (!payload) return
  confirmVisible.value = false
  pendingAction.value = null
  await runAction(payload)
}

async function runAction(payload: { item: QueueItem; action: QueueAction }) {
  const { item, action } = payload
  try {
    if (action === "cancel") {
      await queueStore.cancel(item.id, WORKER_ID)
      ElMessage.success("任务已取消")
    } else if (action === "requeue") {
      await queueStore.retry(item.id, WORKER_ID)
      ElMessage.success("任务已重新入队")
    } else if (action === "pause") {
      await queueStore.pause(item.id, WORKER_ID)
      ElMessage.success("任务已暂停")
    } else if (action === "resume") {
      await queueStore.resume(item.id, WORKER_ID)
      ElMessage.success("任务已恢复")
    } else {
      ElMessage.info(`${ACTION_LABEL[action]}接口待后端接入`)
      return
    }
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "操作失败")
  }
}

const confirmTitle = computed(() => {
  const payload = pendingAction.value
  return payload ? ACTION_LABEL[payload.action] : ""
})

const confirmContent = computed(() => {
  const payload = pendingAction.value
  if (!payload) return ""
  const risk =
    RISK_TEXT[
      payload.action as "release_lock" | "force_stop" | "requeue" | "cancel"
    ] ?? ""
  const drama =
    taskStore.tasks.find((task) => task.id === payload.item.task_id)
      ?.drama_name ?? "当前任务"
  return `确定要对「${drama}」执行${ACTION_LABEL[payload.action]}吗？${risk}`
})
</script>

<template>
  <div class="queue-page">
    <header class="queue-page__header">
      <div>
        <h1 class="queue-page__title">自动化队列</h1>
        <p class="queue-page__subtitle">Worker 锁、租约与任务执行顺序</p>
      </div>
      <ElButton :loading="queueStore.loading" @click="load">
        <el-icon><Refresh /></el-icon>
        刷新
      </ElButton>
    </header>

    <QueueMonitor
      :items="queueStore.items"
      :tasks="taskStore.tasks"
      :loading="queueStore.loading"
      :error="queueStore.error"
      :worker="workerStatus"
      @action="handleAction"
      @retry="load"
    />

    <ConfirmActionDialog
      v-model="confirmVisible"
      :title="confirmTitle"
      :content="confirmContent"
      :confirm-text="pendingAction ? ACTION_LABEL[pendingAction.action] : '确认'"
      @confirm="confirmDanger"
    />
  </div>
</template>

<style scoped>
.queue-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.queue-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.queue-page__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.queue-page__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}
</style>
