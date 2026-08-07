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
  formatDateTime,
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
  (e: "command", payload: { task: TaskView; action: TaskAction }): void
  (e: "retry"): void
}>()

const showTable = computed(() => props.rows.length > 0)

function continueLabel(task: TaskView): string {
  if (!task.queue_state || task.queue_state === "COMPLETED" || task.queue_state === "CANCELLED") {
    return "入队"
  }
  if (task.queue_state === "PAUSED" || task.queue_state === "RETRY_WAIT") {
    return "恢复"
  }
  return "继续"
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
            <th>投放时间</th>
            <th>任务状态</th>
            <th>最后更新时间</th>
            <th class="task-table__operations-head">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="task-table__drama">{{ row.drama_name }}</td>
            <td>{{ getPlatformLabel(row.platform) }}</td>
            <td>{{ formatDateTime(row.available_time) }}</td>
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
                <button
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

.task-table__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
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
