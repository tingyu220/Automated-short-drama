<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ElButton, ElDrawer, ElMessage, ElOption, ElSelect, ElTabPane, ElTabs } from "element-plus"
import { Connection, CopyDocument } from "@element-plus/icons-vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import LinkReadinessTimeline from "@/widgets/link-readiness-timeline/LinkReadinessTimeline.vue"
import {
  getPlatformLabel,
  getStatusColor,
  getStatusLabel
} from "@/shared/utils/status"
import {
  buildLinkReadinessStages,
  formatDateTime,
  getLinkExtractionLabel,
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
  (e: "run", targetStage: string): void
  (e: "confirm-drama-match", locatorKey: string): void
}>()

const activeTab = ref("overview")
const targetStage = ref("LINK_READY")

watch(
  () => props.task?.target_stage,
  (value) => {
    targetStage.value = value === "LINK_EXTRACTION" ? value : "LINK_READY"
  },
  { immediate: true }
)

const stageLabel = computed(() => {
  const labels: Record<string, string> = {
    WAITING_AVAILABLE_TIME: "等待上线时间",
    LINK_EXTRACTION: `${getLinkExtractionLabel(props.task?.platform)}中`,
    DELIVERY_DRAMA: "投放剧目搭建中",
    PROMOTION_CONFIG: "推广内容搭建中",
    LINK_EXTRACTED: "链接已提取",
    LINK_READY: "链接已就绪",
    MANUAL_REVIEW: "待人工处理"
  }
  return labels[props.task?.current_stage ?? ""] ?? props.task?.current_stage ?? "未开始"
})

const linkEntries = computed(() => Object.entries(props.task?.link_set ?? {}))
const configEntries = computed(() => Object.entries(props.task?.promotion_configs ?? {}))

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success("已复制到剪贴板")
  } catch {
    ElMessage.error("复制失败")
  }
}

const dramaMatchCandidates = computed(() => props.task?.drama_match_candidates ?? [])
const readinessStages = computed(() =>
  buildLinkReadinessStages(
    props.task?.current_stage,
    props.task?.status,
    props.task?.steps ?? []
  )
)

const runLabel = computed(() =>
  props.task?.status === "MANUAL_REVIEW" ? "从当前步骤继续" : "执行到此处"
)

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
    size="min(820px, 100vw)"
    destroy-on-close
    @update:model-value="closeDrawer"
  >
    <div v-if="!task" class="task-detail__empty">
      <EmptyState title="未选择任务" description="请先从今日任务列表选择任务" />
    </div>
    <div v-else class="task-detail">
      <ElTabs v-model="activeTab" class="task-detail__tabs">
        <ElTabPane label="概览" name="overview">
          <div class="task-detail__stage-control" aria-label="链接准备阶段">
            <div>
              <span class="task-detail__stage-label">当前阶段</span>
              <strong>{{ stageLabel }}</strong>
            </div>
            <div class="task-detail__stage-actions">
              <ElSelect
                v-model="targetStage"
                aria-label="运行终点"
                size="small"
                style="width: 170px"
              >
                <ElOption label="仅提取链接" value="LINK_EXTRACTION" />
                <ElOption label="搭建链接完成" value="LINK_READY" />
              </ElSelect>
              <ElButton
                type="primary"
                size="small"
                aria-label="运行任务"
                @click="emit('run', targetStage)"
              >
                <el-icon><Connection /></el-icon>
                {{ runLabel }}
              </ElButton>
            </div>
          </div>
          <LinkReadinessTimeline :stages="readinessStages" />
          <section
            v-if="task.failure_code === 'DRAMA_MISMATCH' && dramaMatchCandidates.length"
            class="task-detail__match-confirmation"
          >
            <h4>番茄候选人工确认</h4>
            <p>确认后继续将复用该候选，不会再次按任务时间自动猜测。</p>
            <div
              v-for="candidate in dramaMatchCandidates"
              :key="String(candidate.locator_key)"
              class="task-detail__match-row"
            >
              <span>{{ String(candidate.drama_name ?? '未知剧名') }}</span>
              <span>{{ String(candidate.minute ?? '未知时间') }}</span>
              <ElButton
                type="primary"
                size="small"
                :data-testid="`confirm-drama-match-${String(candidate.locator_key)}`"
                @click="emit('confirm-drama-match', String(candidate.locator_key))"
              >
                确认并继续
              </ElButton>
            </div>
          </section>
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
            <div>
              <dt>投放剧目 ID</dt>
              <dd class="task-detail__mono">{{ task.delivery_drama_id || "—" }}</dd>
            </div>
          </dl>
          <section class="task-detail__outputs" aria-label="链接准备产物">
            <div>
              <h4>{{ getLinkExtractionLabel(task.platform) }}</h4>
              <p v-if="linkEntries.length === 0" class="task-detail__muted">尚未提取</p>
              <ul v-else>
                <li v-for="[key, value] in linkEntries" :key="key">
                  <span>{{ key }}</span>
                  <code>{{ value }}</code>
                  <ElButton :icon="CopyDocument" size="small" circle @click="copyToClipboard(value)" />
                </li>
              </ul>
            </div>
            <div>
              <h4>推广内容</h4>
              <p v-if="configEntries.length === 0" class="task-detail__muted">尚未搭建</p>
              <ul v-else>
                <li v-for="[key, value] in configEntries" :key="key">
                  <span>{{ key }}</span>
                  <code>{{ value }}</code>
                  <ElButton :icon="CopyDocument" size="small" circle @click="copyToClipboard(value)" />
                </li>
              </ul>
            </div>
          </section>
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
  display: flex;
  flex-direction: column;
}

.task-detail__tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.task-detail__tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow-y: auto;
}

.task-detail__overview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 24px;
  padding: 8px 4px;
}

.task-detail__stage-control {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 0 4px 16px;
  padding: 12px;
  background: var(--color-bg-panel-secondary);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-card);
}

.task-detail__stage-label {
  display: block;
  margin-bottom: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.task-detail__stage-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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

.task-detail__outputs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 12px 4px;
}

.task-detail__match-confirmation {
  margin: 12px 4px;
  padding: 12px;
  background: var(--color-bg-panel-secondary);
  border: 1px solid #f1d49a;
  border-radius: var(--radius-card);
}

.task-detail__match-confirmation h4 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--font-size-caption);
}

.task-detail__match-confirmation p {
  margin: 6px 0 10px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.task-detail__match-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 12px;
  align-items: center;
  padding: 8px 0;
  border-top: 1px solid #eadfca;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.task-detail__outputs > div {
  min-width: 0;
  padding: 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
}

.task-detail__outputs h4 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--font-size-caption);
}

.task-detail__outputs ul {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.task-detail__outputs li {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.task-detail__outputs code,
.task-detail__mono {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.task-detail__muted {
  margin: 10px 0 0;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
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

@media (max-width: 720px) {
  .task-detail__stage-control,
  .task-detail__stage-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .task-detail__stage-actions :deep(.el-select) {
    width: 100% !important;
  }

  .task-detail__outputs {
    grid-template-columns: 1fr;
  }
}

</style>
