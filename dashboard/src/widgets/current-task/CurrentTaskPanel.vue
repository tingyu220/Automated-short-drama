<script setup lang="ts">
import { computed } from "vue"
import { ElButton } from "element-plus"
import EmptyState from "@/shared/ui/EmptyState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import LinkReadinessTimeline from "@/widgets/link-readiness-timeline/LinkReadinessTimeline.vue"
import {
  buildLinkReadinessStages,
  formatDuration,
  type QueueItemView,
  type TaskBase
} from "@/entities/task/types"
import { getStatusLabel } from "@/shared/utils/status"

const props = withDefaults(
  defineProps<{
    task: TaskBase | null
    queueItem: QueueItemView | null
    loading?: boolean
    currentStep?: string | null
    recentAction?: string
    nextAction?: string
  }>(),
  {
    task: null,
    queueItem: null,
    loading: false,
    currentStep: null,
    recentAction: "等待步骤结果上报",
    nextAction: "继续当前工作流步骤"
  }
)

const emit = defineEmits<{
  (e: "view"): void
  (e: "pause"): void
  (e: "open-platform"): void
}>()

const stages = computed(() =>
  buildLinkReadinessStages(props.currentStep, props.task?.status)
)

const duration = computed(() => formatDuration(props.task?.updated_at))
const stageLabel = computed(() =>
  props.task ? getStatusLabel(props.queueItem?.state ?? props.task.status) : "—"
)
</script>

<template>
  <section class="current-task" aria-label="当前运行任务">
    <header class="current-task__header">
      <div>
        <h2 class="current-task__title">当前运行任务</h2>
        <p class="current-task__subtitle">链接提取与投放系统搭建实时进度</p>
      </div>
      <div v-if="task" class="current-task__actions">
        <ElButton size="small" @click="emit('open-platform')">打开平台</ElButton>
        <ElButton size="small" type="primary" @click="emit('view')">
          查看详情
        </ElButton>
      </div>
    </header>

    <LoadingSkeleton v-if="loading && !task" :rows="4" />
    <EmptyState
      v-else-if="!task"
      title="当前无运行任务"
      description="任务被 Worker 认领后将在此展示实时进度"
    />
    <template v-else>
      <dl class="current-task__grid">
        <div class="current-task__item">
          <dt>剧名</dt>
          <dd class="current-task__drama">{{ task.drama_name }}</dd>
        </div>
        <div class="current-task__item">
          <dt>平台</dt>
          <dd>{{ task.platform }}</dd>
        </div>
        <div class="current-task__item">
          <dt>队列状态</dt>
          <dd>{{ stageLabel }}</dd>
        </div>
        <div class="current-task__item">
          <dt>运行时长</dt>
          <dd>{{ duration }}</dd>
        </div>
        <div class="current-task__item">
          <dt>Worker</dt>
          <dd>{{ queueItem?.claimed_by ?? "—" }}</dd>
        </div>
        <div class="current-task__item">
          <dt>最近动作</dt>
          <dd>{{ recentAction }}</dd>
        </div>
        <div class="current-task__item current-task__item--wide">
          <dt>下一步动作</dt>
          <dd>{{ nextAction }}</dd>
        </div>
      </dl>
      <div class="current-task__timeline">
        <LinkReadinessTimeline :stages="stages" compact />
      </div>
    </template>
  </section>
</template>

<style scoped>
.current-task {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 280px;
  padding: 20px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-panel);
}

.current-task__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.current-task__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.current-task__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.current-task__actions {
  display: flex;
  gap: 8px;
  flex: none;
}

.current-task__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.current-task__item {
  min-width: 0;
}

.current-task__item--wide {
  grid-column: span 2;
}

.current-task__item dt {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.current-task__item dd {
  margin-top: 6px;
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.current-task__drama {
  color: var(--color-primary-600);
}

.current-task__timeline {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

@media (max-width: 1200px) {
  .current-task__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
