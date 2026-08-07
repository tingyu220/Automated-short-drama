<script setup lang="ts">
import { ref } from "vue"
import { ElDrawer, ElTabPane, ElTabs } from "element-plus"
import EmptyState from "@/shared/ui/EmptyState.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import {
  getPlatformLabel,
  getStatusColor,
  getStatusLabel
} from "@/shared/utils/status"
import {
  formatDateTime,
  type TaskView,
  type WorkflowRunItem
} from "@/entities/task/types"

const props = withDefaults(
  defineProps<{
    open: boolean
    task: TaskView | null
    timeline?: WorkflowRunItem[]
  }>(),
  {
    task: null,
    timeline: () => []
  }
)

const emit = defineEmits<{
  (e: "update:open", value: boolean): void
}>()

const activeTab = ref("overview")

function levelMeta(level: string): { label: string; color: string } {
  const normalized = level.toUpperCase()
  if (normalized === "ERROR" || normalized === "FAILED") {
    return { label: "失败", color: "var(--color-status-failed)" }
  }
  if (normalized === "WARN" || normalized === "WARNING") {
    return { label: "警告", color: "var(--color-status-warning)" }
  }
  return { label: "成功", color: "var(--color-status-success)" }
}

function closeDrawer() {
  emit("update:open", false)
}
</script>

<template>
  <ElDrawer
    :model-value="open"
    :title="task?.drama_name ?? '任务详情'"
    size="820px"
    destroy-on-close
    @update:model-value="closeDrawer"
  >
    <div v-if="!task" class="task-detail__empty">
      <EmptyState title="未选择任务" description="请先从今日任务列表选择任务" />
    </div>
    <div v-else class="task-detail">
      <ElTabs v-model="activeTab" class="task-detail__tabs">
        <ElTabPane label="概览" name="overview">
          <dl class="task-detail__overview">
            <div>
              <dt>剧名</dt>
              <dd>{{ task.drama_name }}</dd>
            </div>
            <div>
              <dt>平台</dt>
              <dd>{{ getPlatformLabel(task.platform) }}</dd>
            </div>
            <div>
              <dt>投放时间</dt>
              <dd>{{ formatDateTime(task.available_time) }}</dd>
            </div>
            <div>
              <dt>队列状态</dt>
              <dd>{{ task.queue_state ? getStatusLabel(task.queue_state) : "—" }}</dd>
            </div>
            <div>
              <dt>任务状态</dt>
              <dd class="task-detail__status">
                <StatusDot :color="getStatusColor(task.status)" :active="task.status === 'RUNNING'" />
                {{ getStatusLabel(task.status) }}
              </dd>
            </div>
            <div>
              <dt>最后更新时间</dt>
              <dd>{{ formatDateTime(task.updated_at) }}</dd>
            </div>
          </dl>
        </ElTabPane>

        <ElTabPane label="执行时间线" name="timeline">
          <EmptyState
            v-if="timeline.length === 0"
            title="暂无执行记录"
            description="工作流步骤执行后将在时间线中展示"
          />
          <ol v-else class="task-detail__timeline">
            <li v-for="(item, index) in timeline" :key="index" class="task-detail__timeline-item">
              <span class="task-detail__timeline-dot">
                <StatusDot :color="levelMeta(item.status).color" />
              </span>
              <div class="task-detail__timeline-body">
                <div class="task-detail__timeline-head">
                  <span class="task-detail__timeline-step">{{ item.step }}</span>
                  <span class="task-detail__timeline-status">
                    {{ levelMeta(item.status).label }}
                  </span>
                </div>
                <p class="task-detail__timeline-meta">
                  {{ formatDateTime(item.started_at) }} → {{ formatDateTime(item.finished_at) }}
                  <span v-if="item.duration_ms">· {{ Math.round(item.duration_ms / 1000) }}s</span>
                </p>
                <p v-if="item.result" class="task-detail__timeline-result">{{ item.result }}</p>
                <p v-if="item.error" class="task-detail__timeline-error">{{ item.error }}</p>
              </div>
            </li>
          </ol>
        </ElTabPane>
      </ElTabs>
    </div>
  </ElDrawer>
</template>

<style scoped>
.task-detail__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 360px;
}

.task-detail__tabs {
  height: calc(100vh - 120px);
}

.task-detail__overview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 24px;
  padding: 8px 4px;
}

.task-detail__overview dt {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.task-detail__overview dd {
  margin-top: 6px;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
}

.task-detail__status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.task-detail__timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  list-style: none;
  padding: 8px 4px;
}

.task-detail__timeline-item {
  position: relative;
  display: flex;
  gap: 12px;
  padding-bottom: 20px;
}

.task-detail__timeline-item:not(:last-child)::before {
  position: absolute;
  top: 18px;
  bottom: 0;
  left: 4px;
  width: 2px;
  background: var(--color-bg-panel-secondary);
  content: "";
}

.task-detail__timeline-dot {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex: none;
  background: var(--color-bg-panel);
}

.task-detail__timeline-body {
  min-width: 0;
  flex: 1;
  padding: 2px 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
}

.task-detail__timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.task-detail__timeline-step {
  color: var(--color-text-primary);
  font-weight: 500;
}

.task-detail__timeline-status {
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.task-detail__timeline-meta,
.task-detail__timeline-result {
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.task-detail__timeline-error {
  margin-top: 6px;
  color: var(--color-status-failed);
  font-size: var(--font-size-caption);
}

</style>
