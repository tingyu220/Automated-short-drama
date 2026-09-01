<script setup lang="ts">
import { computed } from "vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import TaskControlMenu from "@/features/task-control/TaskControlMenu.vue"
import {
  getPlatformLabel,
  getStatusColor,
  getStatusLabel
} from "@/shared/utils/status"
import {
  buildLinkReadinessStages,
  formatDateTime,
  getLinkReadinessStageLabel,
  type LinkReadinessStageStatus,
  type TaskAction,
  type TaskView
} from "@/entities/task/types"

const props = defineProps<{
  rows: TaskView[]
  loading: boolean
  error: string | null
}>()

const emit = defineEmits<{
  (e: "view", task: TaskView): void
  (e: "continue", task: TaskView): void
  (e: "run", payload: { task: TaskView; targetStage: "LINK_EXTRACTION" | "LINK_READY" }): void
  (e: "command", payload: { task: TaskView; action: TaskAction }): void
  (e: "retry"): void
}>()

const showTable = computed(() => props.rows.length > 0)

function canStart(task: TaskView): boolean {
  const status = task.status?.toUpperCase()
  if (
    status === "LINK_READY" ||
    status === "COMPLETED" ||
    status === "CANCELLED"
  ) {
    return false
  }
  return (
    !task.queue_state ||
    task.queue_state === "COMPLETED" ||
    task.queue_state === "CANCELLED"
  )
}

function continueLabel(task: TaskView): string {
  if (
    !task.queue_state ||
    task.queue_state === "COMPLETED" ||
    task.queue_state === "CANCELLED" ||
    task.queue_state === "DRY_RUN"
  ) {
    return "入队"
  }
  if (task.queue_state === "PAUSED" || task.queue_state === "RETRY_WAIT") {
    return "恢复"
  }
  return "继续"
}

function stageStatus(task: TaskView): LinkReadinessStageStatus {
  if (task.status.toUpperCase() === "LINK_EXTRACTED") return "done"
  const stages = buildLinkReadinessStages(task.current_stage, task.status, [], task.platform)
  return (
    stages.find((stage) => stage.status === "failed")?.status ??
    stages.find((stage) => stage.status === "current")?.status ??
    (stages.every((stage) => stage.status === "done") ? "done" : "pending")
  )
}

function endTypeLabel(endType: string): string {
  if (endType === "MINIPROGRAM") return "小程序"
  return "原生"
}
</script>

<template>
  <div class="task-table">
    <ErrorState
      v-if="error"
      :message="error"
      retry-text="重新加载"
      @retry="emit('retry')"
    />
    <LoadingSkeleton v-else-if="loading && !showTable" :rows="6" />
    <EmptyState
      v-else-if="!showTable"
      title="暂无任务"
      description="当前筛选条件下没有找到任务"
    />
    <div v-else class="task-table__scroll">
      <table class="task-table__table">
        <thead>
          <tr>
            <th>剧名</th>
            <th>平台</th>
            <th>产线</th>
            <th>投放时间</th>
            <th>当前阶段</th>
            <th>任务状态</th>
            <th>最后更新时间</th>
            <th class="task-table__operations-head">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="task-table__drama">{{ row.drama_name }}</td>
            <td>{{ getPlatformLabel(row.platform) }}</td>
            <td>
              <span
                class="task-table__end-type"
                :class="row.end_type === 'MINIPROGRAM' ? 'is-mp' : 'is-native'"
              >
                {{ endTypeLabel(row.end_type) }}
              </span>
            </td>
            <td>{{ formatDateTime(row.available_time) }}</td>
            <td>
              <span
                class="task-table__stage"
                :class="`is-${stageStatus(row)}`"
              >
                {{ getLinkReadinessStageLabel(row.current_stage, row.status, row.platform) }}
              </span>
            </td>
            <td>
              <span class="task-table__status">
                <StatusDot :color="getStatusColor(row.status)" :active="row.status === 'RUNNING'" />
                {{ getStatusLabel(row.status) }}
              </span>
            </td>
            <td>{{ formatDateTime(row.updated_at) }}</td>
            <td class="task-table__operations">
              <div class="task-table__actions">
                <button
                  class="task-table__action-button"
                  type="button"
                  @click="emit('view', row)"
                >
                  查看
                </button>
                <template v-if="canStart(row)">
                  <button
                    class="task-table__action-button"
                    type="button"
                    :aria-label="`提取链接：${row.drama_name}`"
                    @click="emit('run', { task: row, targetStage: 'LINK_EXTRACTION' })"
                  >
                    提取链接
                  </button>
                  <button
                    class="task-table__action-button task-table__action-button--primary"
                    type="button"
                    :aria-label="`搭建链接：${row.drama_name}`"
                    @click="emit('run', { task: row, targetStage: 'LINK_READY' })"
                  >
                    搭建链接
                  </button>
                </template>
                <button
                  v-else
                  class="task-table__action-button task-table__action-button--primary"
                  type="button"
                  @click="emit('continue', row)"
                >
                  {{ continueLabel(row) }}
                </button>
                <TaskControlMenu :task="row" @command="emit('command', $event)" />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.task-table {
  min-height: 240px;
}

.task-table__scroll {
  overflow-x: auto;
}

.task-table__table {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
  font-size: var(--font-size-table);
}

.task-table__table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 10px 12px;
  background: var(--color-bg-panel-secondary);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #e5e7eb;
}

.task-table__table td {
  padding: 10px 12px;
  color: var(--color-text-primary);
  white-space: nowrap;
  border-bottom: 1px solid #f0f1f3;
}

.task-table__table tbody tr {
  height: 48px;
  transition: background 0.15s ease;
}

.task-table__table tbody tr:hover {
  background: var(--color-bg-panel-secondary);
}

.task-table__table tbody tr:last-child td {
  border-bottom: none;
}

.task-table__drama {
  max-width: 220px;
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
}

.task-table__end-type {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.task-table__end-type.is-native {
  background: #e0edff;
  color: #2563eb;
}

.task-table__end-type.is-mp {
  background: #e0f5e9;
  color: #059669;
}

.task-table__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
}

.task-table__stage {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border: 1px solid #dbe2f0;
  border-radius: 999px;
  color: var(--color-primary-600);
  background: #f7f9ff;
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.task-table__stage.is-done {
  border-color: color-mix(in srgb, var(--color-status-success) 28%, transparent);
  color: var(--color-status-success);
  background: color-mix(in srgb, var(--color-status-success) 8%, transparent);
}

.task-table__stage.is-current {
  border-color: color-mix(in srgb, var(--color-status-running) 28%, transparent);
  color: var(--color-status-running);
  background: color-mix(in srgb, var(--color-status-running) 8%, transparent);
}

.task-table__stage.is-failed {
  border-color: color-mix(in srgb, var(--color-status-failed) 28%, transparent);
  color: var(--color-status-failed);
  background: color-mix(in srgb, var(--color-status-failed) 8%, transparent);
}

.task-table__mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  color: var(--color-text-secondary);
}

.task-table__operations {
  position: sticky;
  right: 0;
  background: var(--color-bg-panel);
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.task-table__operations-head {
  right: 0;
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.task-table__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.task-table__action-button {
  height: 28px;
  padding: 0 10px;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.task-table__action-button:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.task-table__action-button--primary {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
</style>
