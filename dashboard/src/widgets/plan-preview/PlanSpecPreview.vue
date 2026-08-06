<script setup lang="ts">
import { computed, ref } from "vue"
import { ElButton } from "element-plus"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import { getPlanStatusMeta } from "./plan-status"
import type { PlanView } from "@/app/stores/plan"

const props = withDefaults(
  defineProps<{
    plan: PlanView | null
    loading?: boolean
    error?: string | null
  }>(),
  {
    loading: false,
    error: null
  }
)

const emit = defineEmits<{
  (e: "retry"): void
}>()

const showRaw = ref(false)

interface SpecField {
  label: string
  value: string
}

const sections = computed(() => {
  const plan = props.plan
  if (!plan) return []
  const status = getPlanStatusMeta(plan.status)
  const groups: Array<{ title: string; fields: SpecField[] }> = [
    {
      title: "基础信息",
      fields: [
        { label: "任务名称", value: plan.taskName },
        { label: "剧名", value: plan.dramaName },
        { label: "计划类型", value: plan.planType },
        { label: "平台", value: plan.platform },
        { label: "外部任务ID", value: plan.externalTaskId },
        { label: "创建时间", value: plan.createdAt }
      ]
    },
    {
      title: "账户与CID",
      fields: [
        { label: "账户数", value: plan.accountCount },
        { label: "CID数", value: plan.cidCount }
      ]
    },
    {
      title: "推广内容",
      fields: [
        { label: "IAA 链接", value: "—" },
        { label: "9.9 链接", value: "—" },
        { label: "2.9 链接", value: "—" }
      ]
    },
    {
      title: "抖音号",
      fields: [{ label: "抖音号", value: "—" }]
    },
    {
      title: "预设",
      fields: [
        { label: "开户预设", value: "—" },
        { label: "广告预设", value: "—" }
      ]
    },
    {
      title: "产品",
      fields: [
        { label: "产品库", value: "—" },
        { label: "专辑ID", value: "—" }
      ]
    },
    {
      title: "素材分组",
      fields: [
        { label: "素材数", value: plan.materialCount },
        { label: "素材组数", value: plan.materialGroupCount }
      ]
    },
    {
      title: "项目数",
      fields: [{ label: "预计项目数", value: plan.expectedProjectCount }]
    },
    {
      title: "任务名称",
      fields: [{ label: "任务名称", value: plan.taskName }]
    },
    {
      title: "校验结果",
      fields: [
        { label: "校验状态", value: status.label },
        { label: "提交状态", value: plan.submitStatus }
      ]
    }
  ]
  return groups
})

const statusMeta = computed(() => getPlanStatusMeta(props.plan?.status))
</script>

<template>
  <div class="plan-preview">
    <ErrorState
      v-if="error"
      :message="error"
      retry-text="重新加载"
      @retry="emit('retry')"
    />
    <LoadingSkeleton v-else-if="loading && !plan" :rows="5" />
    <EmptyState
      v-else-if="!plan"
      title="暂无计划数据"
      description="从列表中选择一个计划查看 PlanSpec 详情"
    />
    <template v-else>
      <div class="plan-preview__header">
        <div class="plan-preview__status">
          <StatusDot :color="statusMeta.color" :active="statusMeta.active" />
          <span>{{ statusMeta.label }}</span>
        </div>
        <ElButton size="small" @click="showRaw = !showRaw">
          {{ showRaw ? "查看结构化视图" : "查看原始数据" }}
        </ElButton>
      </div>

      <pre v-if="showRaw" class="plan-preview__raw">{{
        JSON.stringify(plan, null, 2)
      }}</pre>

      <div v-else class="plan-preview__sections">
        <section
          v-for="group in sections"
          :key="group.title"
          class="plan-preview__section"
        >
          <h3 class="plan-preview__section-title">{{ group.title }}</h3>
          <dl class="plan-preview__fields">
            <div
              v-for="field in group.fields"
              :key="field.label"
              class="plan-preview__field"
            >
              <dt>{{ field.label }}</dt>
              <dd>{{ field.value }}</dd>
            </div>
          </dl>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.plan-preview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 240px;
}

.plan-preview__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.plan-preview__status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  font-weight: 500;
}

.plan-preview__sections {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.plan-preview__section {
  padding: 14px;
  background: var(--color-bg-panel-secondary);
  border: 1px solid #eef0f3;
  border-radius: var(--radius-card);
}

.plan-preview__section-title {
  margin-bottom: 10px;
  color: var(--color-text-primary);
  font-size: var(--font-size-caption);
  font-weight: 600;
}

.plan-preview__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.plan-preview__field {
  min-width: 0;
}

.plan-preview__field dt {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.plan-preview__field dd {
  margin-top: 4px;
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-preview__raw {
  overflow: auto;
  padding: 14px;
  color: var(--color-text-secondary);
  background: var(--color-bg-panel-secondary);
  border: 1px solid #eef0f3;
  border-radius: var(--radius-card);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 900px) {
  .plan-preview__sections,
  .plan-preview__fields {
    grid-template-columns: 1fr;
  }
}
</style>
