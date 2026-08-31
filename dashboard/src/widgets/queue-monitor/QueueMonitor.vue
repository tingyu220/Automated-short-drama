<script setup lang="ts">
import { computed, ref } from "vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import {
  formatDateTime,
  type QueueItemView,
  type TaskBase
} from "@/entities/task/types"

export type QueueAction =
  | "requeue"
  | "cancel"
  | "pause"
  | "resume"

export interface QueueWorkerStatus {
  online: boolean
  heartbeatText: string
  currentTask: string
  leaseUntil: string
  platform: string
  runtime: string
}

interface QueueActionOption {
  key: QueueAction
  label: string
  danger?: boolean
}

interface QueueGroup {
  key: string
  label: string
  states: string[]
}

const GROUPS: QueueGroup[] = [
  { key: "waiting", label: "等待时间", states: ["WAITING_TIME"] },
  { key: "queued", label: "排队中", states: ["QUEUED"] },
  { key: "running", label: "运行中", states: ["CLAIMED", "RUNNING"] },
  { key: "retry", label: "重试等待", states: ["RETRY_WAIT"] },
  { key: "manual", label: "人工处理", states: ["MANUAL_REVIEW"] },
  { key: "paused", label: "暂停", states: ["PAUSED"] },
  { key: "failed", label: "失败", states: ["FAILED"] }
]

const SELECTABLE_GROUPS = new Set(["queued", "waiting"])

const props = defineProps<{
  items: QueueItemView[]
  tasks: TaskBase[]
  loading: boolean
  error: string | null
  worker: QueueWorkerStatus
}>()

const emit = defineEmits<{
  (e: "action", payload: { item: QueueItemView; action: QueueAction }): void
  (e: "batch-action", payload: { items: QueueItemView[]; action: QueueAction }): void
  (e: "retry"): void
}>()

/* ── 批量选择 ── */
const selectedIds = ref<Set<string>>(new Set())

function isSelectable(groupKey: string): boolean {
  return SELECTABLE_GROUPS.has(groupKey)
}

function isSelected(id: string): boolean {
  return selectedIds.value.has(id)
}

function toggleRow(id: string) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function isAllSelected(rows: { id: string }[]): boolean {
  return rows.length > 0 && rows.every((r) => selectedIds.value.has(r.id))
}

function isPartialSelected(rows: { id: string }[]): boolean {
  const n = rows.filter((r) => selectedIds.value.has(r.id)).length
  return n > 0 && n < rows.length
}

function toggleSelectAll(rows: { id: string }[]) {
  const next = new Set(selectedIds.value)
  if (isAllSelected(rows)) {
    rows.forEach((r) => next.delete(r.id))
  } else {
    rows.forEach((r) => next.add(r.id))
  }
  selectedIds.value = next
}

function selectedCount(rows: { id: string }[]): number {
  return rows.filter((r) => selectedIds.value.has(r.id)).length
}

function selectedRows(rows: QueueItemView[]): QueueItemView[] {
  return rows.filter((r) => selectedIds.value.has(r.id))
}

function clearGroupSelection(rows: { id: string }[]) {
  const next = new Set(selectedIds.value)
  rows.forEach((r) => next.delete(r.id))
  selectedIds.value = next
}

function batchActionsFor(groupKey: string): QueueActionOption[] {
  switch (groupKey) {
    case "queued":
      return [
        { key: "pause", label: "批量暂停" },
        { key: "cancel", label: "批量取消", danger: true }
      ]
    case "waiting":
      return [{ key: "cancel", label: "批量取消", danger: true }]
    default:
      return []
  }
}

function emitBatchAction(items: QueueItemView[], action: QueueAction) {
  emit("batch-action", { items, action })
}

const vIndeterminate = {
  updated(el: HTMLInputElement, binding: { value: boolean }) {
    el.indeterminate = binding.value
  },
  mounted(el: HTMLInputElement, binding: { value: boolean }) {
    el.indeterminate = binding.value
  }
}

const groups = computed(() =>
  GROUPS.map((group) => ({
    ...group,
    rows: props.items
      .filter((item) => group.states.includes(item.state))
      .map((item) => {
        const task = props.tasks.find((entry) => entry.id === item.task_id)
        return {
          ...item,
          dramaName: item.drama_name || task?.drama_name || `任务 ${item.task_id}`
        }
      })
  }))
)

function actionsFor(item: QueueItemView): QueueActionOption[] {
  switch (item.state) {
    case "CLAIMED":
    case "RUNNING":
      return [
        { key: "pause", label: "暂停" },
        { key: "cancel", label: "取消", danger: true }
      ]
    case "QUEUED":
      return [
        { key: "pause", label: "暂停" },
        { key: "cancel", label: "取消", danger: true }
      ]
    case "WAITING_TIME":
      return [{ key: "cancel", label: "取消", danger: true }]
    case "RETRY_WAIT":
    case "MANUAL_REVIEW":
      return [
        { key: "requeue", label: "重新入队", danger: true },
        { key: "cancel", label: "取消", danger: true }
      ]
    case "PAUSED":
      return [
        { key: "resume", label: "恢复" },
        { key: "cancel", label: "取消", danger: true }
      ]
    case "FAILED":
      return [{ key: "requeue", label: "重新入队", danger: true }]
    default:
      return []
  }
}

const workerFields = computed(() => [
  {
    label: "Worker 状态",
    value: props.worker.online ? "在线" : "离线",
    color: props.worker.online
      ? "var(--color-status-success)"
      : "var(--color-status-pending)",
    active: props.worker.online
  },
  { label: "心跳", value: props.worker.heartbeatText, color: "", active: false },
  { label: "当前锁定任务", value: props.worker.currentTask, color: "", active: false },
  { label: "租约过期时间", value: props.worker.leaseUntil, color: "", active: false },
  { label: "当前平台", value: props.worker.platform, color: "", active: false },
  { label: "运行时长", value: props.worker.runtime, color: "", active: false }
])
</script>

<template>
  <div class="queue-monitor">
    <section class="queue-monitor__worker" aria-label="Worker 状态">
      <header class="queue-monitor__worker-header">
        <h2 class="queue-monitor__title">Worker 状态</h2>
        <span class="queue-monitor__count">队列 {{ items.length }} 项</span>
      </header>
      <dl class="queue-monitor__worker-grid">
        <div
          v-for="field in workerFields"
          :key="field.label"
          class="queue-monitor__worker-item"
        >
          <dt>{{ field.label }}</dt>
          <dd>
            <StatusDot
              v-if="field.color"
              :color="field.color"
              :active="field.active"
            />
            {{ field.value }}
          </dd>
        </div>
      </dl>
    </section>

    <ErrorState
      v-if="error"
      :message="error"
      retry-text="重新加载"
      @retry="emit('retry')"
    />
    <LoadingSkeleton v-else-if="loading && items.length === 0" :rows="6" />
    <EmptyState
      v-else-if="items.length === 0"
      title="队列为空"
      description="暂无等待执行的自动化任务"
    />
    <section v-else class="queue-monitor__groups" aria-label="队列分组列表">
      <div
        v-for="group in groups"
        :key="group.key"
        class="queue-monitor__group"
      >
        <header class="queue-monitor__group-header">
          <h3 class="queue-monitor__group-title">{{ group.label }}</h3>
          <span class="queue-monitor__group-count">{{ group.rows.length }}</span>
          <div
            v-if="isSelectable(group.key) && selectedCount(group.rows) > 0"
            class="queue-monitor__batch-bar"
          >
            <span class="queue-monitor__batch-info">已选 {{ selectedCount(group.rows) }} 项</span>
            <button
              v-for="option in batchActionsFor(group.key)"
              :key="option.key"
              type="button"
              class="queue-monitor__batch-btn"
              :class="{ 'queue-monitor__batch-btn--danger': option.danger }"
              @click="emitBatchAction(selectedRows(group.rows), option.key)"
            >
              {{ option.label }}
            </button>
            <button
              type="button"
              class="queue-monitor__batch-clear"
              @click="clearGroupSelection(group.rows)"
            >
              清除选择
            </button>
          </div>
        </header>
        <p v-if="group.rows.length === 0" class="queue-monitor__group-empty">
          暂无任务
        </p>
        <div v-else class="queue-monitor__scroll">
          <table class="queue-monitor__table">
            <thead>
              <tr>
                <th v-if="isSelectable(group.key)" class="queue-monitor__check-head">
                  <input
                    type="checkbox"
                    :checked="isAllSelected(group.rows)"
                    v-indeterminate="isPartialSelected(group.rows)"
                    @change="toggleSelectAll(group.rows)"
                  />
                </th>
                <th>剧名</th>
                <th>优先级</th>
                <th>可执行时间</th>
                <th>重试次数</th>
                <th>租约</th>
                <th class="queue-monitor__operations-head">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in group.rows" :key="row.id">
                <td v-if="isSelectable(group.key)" class="queue-monitor__check">
                  <input
                    type="checkbox"
                    :checked="isSelected(row.id)"
                    @change="toggleRow(row.id)"
                  />
                </td>
                <td class="queue-monitor__drama">{{ row.dramaName }}</td>
                <td>{{ row.priority }}</td>
                <td>{{ formatDateTime(row.available_at) }}</td>
                <td>{{ row.attempt_count }}</td>
                <td>{{ formatDateTime(row.lease_until) }}</td>
                <td class="queue-monitor__operations">
                  <div class="queue-monitor__actions">
                    <button
                      v-for="option in actionsFor(row)"
                      :key="option.key"
                      type="button"
                      class="queue-monitor__action"
                      :class="{
                        'queue-monitor__action--danger': option.danger
                      }"
                      @click="emit('action', { item: row, action: option.key })"
                    >
                      {{ option.label }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.queue-monitor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 260px;
}

.queue-monitor__worker {
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-panel);
}

.queue-monitor__worker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.queue-monitor__title,
.queue-monitor__group-title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.queue-monitor__count {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.queue-monitor__worker-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.queue-monitor__worker-item {
  min-width: 0;
}

.queue-monitor__worker-item dt {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.queue-monitor__worker-item dd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-monitor__groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.queue-monitor__group {
  padding: 14px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.queue-monitor__group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.queue-monitor__group-title {
  font-size: var(--font-size-body);
}

.queue-monitor__group-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  color: var(--color-text-secondary);
  background: var(--color-bg-panel-secondary);
  border-radius: 999px;
  font-size: var(--font-size-caption);
  font-weight: 600;
}

.queue-monitor__batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.queue-monitor__batch-info {
  color: var(--color-primary);
  font-size: var(--font-size-caption);
  font-weight: 600;
}

.queue-monitor__batch-btn {
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-primary);
  font-size: var(--font-size-caption);
  cursor: pointer;
  transition: background 0.15s ease;
}

.queue-monitor__batch-btn:hover {
  background: var(--color-primary);
  color: #fff;
}

.queue-monitor__batch-btn--danger {
  border-color: var(--color-status-failed);
  color: var(--color-status-failed);
}

.queue-monitor__batch-btn--danger:hover {
  background: var(--color-status-failed);
  color: #fff;
}

.queue-monitor__batch-clear {
  height: 26px;
  padding: 0 8px;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  cursor: pointer;
}

.queue-monitor__batch-clear:hover {
  border-color: var(--color-text-secondary);
}

.queue-monitor__check-head,
.queue-monitor__check {
  width: 36px;
  min-width: 36px;
  text-align: center;
}

.queue-monitor__check-head input,
.queue-monitor__check input {
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.queue-monitor__group-empty {
  padding: 8px 0;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.queue-monitor__scroll {
  overflow-x: auto;
}

.queue-monitor__table {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
  font-size: var(--font-size-table);
}

.queue-monitor__table th {
  padding: 8px 10px;
  color: var(--color-text-secondary);
  background: var(--color-bg-panel-secondary);
  font-size: var(--font-size-caption);
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #eef0f3;
}

.queue-monitor__table td {
  padding: 8px 10px;
  color: var(--color-text-primary);
  white-space: nowrap;
  border-bottom: 1px solid #f0f1f3;
}

.queue-monitor__table tbody tr {
  height: 40px;
  transition: background 0.15s ease;
}

.queue-monitor__table tbody tr:hover {
  background: var(--color-bg-panel-secondary);
}

.queue-monitor__table tbody tr:last-child td {
  border-bottom: none;
}

.queue-monitor__drama {
  max-width: 220px;
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
}

.queue-monitor__operations {
  position: sticky;
  right: 0;
  background: var(--color-bg-panel);
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.queue-monitor__operations-head {
  right: 0;
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.queue-monitor__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.queue-monitor__action {
  height: 26px;
  padding: 0 8px;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.queue-monitor__action:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.queue-monitor__action--danger {
  color: var(--color-status-failed);
}

.queue-monitor__action--danger:hover {
  border-color: var(--color-status-failed);
  color: var(--color-status-failed);
}

@media (max-width: 1200px) {
  .queue-monitor__worker-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
