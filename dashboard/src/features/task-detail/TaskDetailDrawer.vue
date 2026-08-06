<script setup lang="ts">
import { computed, ref } from "vue"
import { ElDrawer, ElTabPane, ElTabs } from "element-plus"
import EmptyState from "@/shared/ui/EmptyState.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import LinkSourceCard from "@/widgets/link-source/LinkSourceCard.vue"
import { getStatusColor, getStatusLabel } from "@/shared/utils/status"
import {
  formatDateTime,
  formatDuration,
  WORKFLOW_STEPS,
  type PromotionLink,
  type TaskView,
  type WorkflowRunItem
} from "@/entities/task/types"

const props = withDefaults(
  defineProps<{
    open: boolean
    task: TaskView | null
    timeline?: WorkflowRunItem[]
    links?: PromotionLink[]
  }>(),
  {
    task: null,
    timeline: () => [],
    links: () => []
  }
)

const emit = defineEmits<{
  (e: "update:open", value: boolean): void
}>()

const activeTab = ref("overview")

const linkTabs = computed<PromotionLink[]>(() => {
  const base: Array<{
    key: PromotionLink["key"]
    label: string
    field: string | null | undefined
  }> = [
    { key: "iaa", label: "IAA", field: props.task?.iaa },
    { key: "iap_9_9", label: "9.9", field: props.task?.price_9_9 },
    { key: "iap_2_9", label: "2.9", field: props.task?.price_2_9 }
  ]
  return base.map(({ key, label, field }) => {
    const provided = props.links.find((link) => link.key === key)
    if (provided) return provided
    return {
      key,
      label,
      status: field ?? "",
      source: "—",
      entry: "—",
      method: "—",
      url: ""
    }
  })
})

const stageLabel = computed(() => {
  if (!props.task) return "—"
  if (props.task.current_step) {
    const step = WORKFLOW_STEPS.find(
      (item) => item.key === props.task?.current_step
    )
    if (step) return step.label
  }
  return getStatusLabel(props.task.queue_state ?? props.task.status)
})

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
              <dd>{{ task.platform }}</dd>
            </div>
            <div>
              <dt>投放时间</dt>
              <dd>{{ formatDateTime(task.available_time) }}</dd>
            </div>
            <div>
              <dt>当前阶段</dt>
              <dd>{{ stageLabel }}</dd>
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
              <dt>专辑ID</dt>
              <dd class="task-detail__mono">{{ task.album_id ?? "—" }}</dd>
            </div>
            <div>
              <dt>产品库</dt>
              <dd class="task-detail__mono">{{ task.product_library ?? "—" }}</dd>
            </div>
            <div>
              <dt>PlanSpec</dt>
              <dd class="task-detail__mono">{{ task.plan_spec ?? "未生成" }}</dd>
            </div>
            <div>
              <dt>计划状态</dt>
              <dd>{{ task.plan_status ? getStatusLabel(task.plan_status) : "—" }}</dd>
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
                <StatusDot :color="getStatusColor(item.status)" />
              </span>
              <div class="task-detail__timeline-body">
                <div class="task-detail__timeline-head">
                  <span class="task-detail__timeline-step">{{ item.step }}</span>
                  <span class="task-detail__timeline-status">
                    {{ getStatusLabel(item.status) }}
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

        <ElTabPane label="推广链接" name="links">
          <div class="task-detail__links">
            <LinkSourceCard v-for="link in linkTabs" :key="link.key" :link="link" />
          </div>
        </ElTabPane>

        <ElTabPane label="账户" name="accounts">
          <EmptyState
            title="账户数据占位"
            description="飞书账户实时数据将在账户功能阶段接入"
          />
        </ElTabPane>

        <ElTabPane label="外部资产" name="assets">
          <EmptyState
            title="外部资产占位"
            description="素材、截图与外部任务资产将在后续阶段接入"
          />
        </ElTabPane>

        <ElTabPane label="PlanSpec" name="planspec">
          <EmptyState
            title="PlanSpec 占位"
            description="结构化计划将在计划管理阶段展示"
          />
        </ElTabPane>

        <ElTabPane label="异常" name="exceptions">
          <EmptyState
            title="暂无异常"
            description="任务异常将在此集中展示"
          />
        </ElTabPane>

        <ElTabPane label="执行记录" name="records">
          <EmptyState
            title="执行记录占位"
            description="业务台账与操作审计将在系统记录阶段接入"
          />
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

.task-detail__mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
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

.task-detail__links {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 4px;
}
</style>
