<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ElButton, ElMessage } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import ConfirmActionDialog from "@/shared/ui/ConfirmActionDialog.vue"
import PageHeader from "@/shared/ui/PageHeader.vue"
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
  isLeaseActive
} from "@/entities/task/types"

const queueStore = useQueueStore()
const taskStore = useTaskStore()
const systemStore = useSystemStore()


const confirmVisible = ref(false)
const pendingAction = ref<{ item: QueueItem; action: QueueAction } | null>(null)
const batchConfirmVisible = ref(false)
const pendingBatch = ref<{ items: QueueItem[]; action: QueueAction } | null>(null)

const RISK_TEXT: Record<
  "requeue" | "cancel",
  string
> = {
  requeue:
    "重新入队会把任务放回排队中并重置重试次数，正在执行的步骤不会继续。",
  cancel: "取消任务会终止后续自动化流程，且无法自动恢复。"
}

const ACTION_LABEL: Record<QueueAction, string> = {
  requeue: "重新入队",
  cancel: "取消任务",
  pause: "暂停",
  resume: "恢复"
}

async function load() {
  await Promise.all([
    queueStore.fetchQueue(),
    // 队列可能包含前几天未完成的任务，不能只加载今日剧目。
    taskStore.fetchTasks(),
    systemStore.fetchHealth()
  ])
}

onMounted(load)

const runningItem = computed(
  () =>
    queueStore.items.find(
      (item) =>
        (item.state === "RUNNING" || item.state === "CLAIMED") &&
        isLeaseActive(item)
    ) ?? null
)

const workerStatus = computed<QueueWorkerStatus>(() => {
  const online = systemStore.isWorkerOnline()
  const item = runningItem.value
  return {
    online,
    heartbeatText: online ? "正常" : "离线",
    currentTask: item
      ? (taskStore.tasks.find((entry) => entry.id === item.task_id)
          ?.drama_name ?? "—")
      : "—",
    leaseUntil: item?.lease_until
      ? formatDateTime(item.lease_until)
      : "—",
    platform: item
      ? (taskStore.tasks.find((entry) => entry.id === item.task_id)
          ?.platform ?? "—")
      : "—",
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
  const workerId = systemStore.activeWorkerId
  if (!workerId) {
    ElMessage.error("Worker 离线，无法控制已认领任务")
    return
  }
  try {
    if (action === "cancel") {
      await queueStore.cancel(item.id, workerId)
      ElMessage.success("任务已取消")
    } else if (action === "requeue") {
      await queueStore.retry(item.id, workerId)
      ElMessage.success("任务已重新入队")
    } else if (action === "pause") {
      await queueStore.pause(item.id, workerId)
      ElMessage.success("任务已暂停")
    } else if (action === "resume") {
      await queueStore.resume(item.id, workerId)
      ElMessage.success("任务已恢复")
    }
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "操作失败")
  }
}

/* ── 批量操作 ── */
function handleBatchAction(payload: { items: QueueItem[]; action: QueueAction }) {
  if (payload.action === "cancel") {
    pendingBatch.value = payload
    batchConfirmVisible.value = true
    return
  }
  void runBatchAction(payload)
}

async function confirmBatch() {
  const payload = pendingBatch.value
  if (!payload) return
  batchConfirmVisible.value = false
  pendingBatch.value = null
  await runBatchAction(payload)
}

async function runBatchAction(payload: { items: QueueItem[]; action: QueueAction }) {
  const { items, action } = payload
  const workerId = systemStore.activeWorkerId
  if (!workerId) {
    ElMessage.error("Worker 离线，无法控制已认领任务")
    return
  }
  let ok = 0
  let fail = 0
  for (const item of items) {
    try {
      if (action === "cancel") await queueStore.cancel(item.id, workerId)
      else if (action === "pause") await queueStore.pause(item.id, workerId)
      else if (action === "resume") await queueStore.resume(item.id, workerId)
      else if (action === "requeue") await queueStore.retry(item.id, workerId)
      ok++
    } catch {
      fail++
    }
  }
  if (ok) ElMessage.success(`${ok} 项操作成功`)
  if (fail) ElMessage.warning(`${fail} 项操作失败`)
  await load()
}

const batchConfirmContent = computed(() => {
  const p = pendingBatch.value
  if (!p) return ""
  const names = p.items
    .map((i) => taskStore.tasks.find((t) => t.id === i.task_id)?.drama_name ?? i.drama_name ?? "未知")
    .join("、")
  return `确定要对以下 ${p.items.length} 项执行${ACTION_LABEL[p.action]}吗？\n${names}`
})

const confirmTitle = computed(() => {
  const payload = pendingAction.value
  return payload ? ACTION_LABEL[payload.action] : ""
})

const confirmContent = computed(() => {
  const payload = pendingAction.value
  if (!payload) return ""
  const risk = RISK_TEXT[payload.action as "requeue" | "cancel"] ?? ""
  const drama =
    taskStore.tasks.find((task) => task.id === payload.item.task_id)
      ?.drama_name ?? "当前任务"
  return `确定要对「${drama}」执行${ACTION_LABEL[payload.action]}吗？${risk}`
})
</script>

<template>
  <div class="queue-page">
    <PageHeader
      title="自动化队列"
      subtitle="Worker 锁、租约与任务执行顺序"
    >
      <template #actions>
        <ElButton :loading="queueStore.loading" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </ElButton>
      </template>
    </PageHeader>

    <QueueMonitor
      :items="queueStore.items"
      :tasks="taskStore.tasks"
      :loading="queueStore.loading"
      :error="queueStore.error"
      :worker="workerStatus"
      @action="handleAction"
      @batch-action="handleBatchAction"
      @retry="load"
    />

    <ConfirmActionDialog
      v-model="confirmVisible"
      :title="confirmTitle"
      :content="confirmContent"
      :confirm-text="pendingAction ? ACTION_LABEL[pendingAction.action] : '确认'"
      @confirm="confirmDanger"
    />

    <ConfirmActionDialog
      v-model="batchConfirmVisible"
      :title="pendingBatch ? ACTION_LABEL[pendingBatch.action] : ''"
      :content="batchConfirmContent"
      :confirm-text="pendingBatch ? ACTION_LABEL[pendingBatch.action] : '确认'"
      @confirm="confirmBatch"
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
