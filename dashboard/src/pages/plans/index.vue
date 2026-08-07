<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ElButton, ElDrawer } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import PageHeader from "@/shared/ui/PageHeader.vue"
import PaginationBar from "@/shared/ui/PaginationBar.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import PlanSpecPreview from "@/widgets/plan-preview/PlanSpecPreview.vue"
import { getPlanStatusMeta } from "@/widgets/plan-preview/plan-status"
import { usePlanStore, type PlanView } from "@/app/stores/plan"
import { formatDateTime } from "@/entities/task/types"

const planStore = usePlanStore()

const drawerOpen = ref(false)
const selectedPlan = ref<PlanView | null>(null)
const page = ref(1)
const pageSize = ref(10)

const pagedPlans = computed(() =>
  planStore.plans.slice(
    (page.value - 1) * pageSize.value,
    page.value * pageSize.value
  )
)

async function load() {
  await planStore.fetchPlans()
}

onMounted(load)

function openPlan(plan: PlanView) {
  selectedPlan.value = plan
  drawerOpen.value = true
}
</script>

<template>
  <div class="plans-page">
    <PageHeader
      title="计划管理"
      subtitle="PlanSpec、校验结果、素材分组与提交状态"
    >
      <template #actions>
        <ElButton :loading="planStore.loading" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </ElButton>
      </template>
    </PageHeader>

    <ErrorState
      v-if="planStore.error"
      :message="planStore.error"
      retry-text="重新加载"
      @retry="load"
    />
    <LoadingSkeleton v-else-if="planStore.loading && planStore.plans.length === 0" :rows="6" />
    <EmptyState
      v-else-if="planStore.plans.length === 0"
      title="暂无计划"
      description="任务完成后会在此生成交付计划"
    />
    <div v-else class="plans-page__scroll">
      <table class="plans-page__table">
        <thead>
          <tr>
            <th>任务名称</th>
            <th>剧名</th>
            <th>计划类型</th>
            <th>账户数</th>
            <th>CID数</th>
            <th>素材数</th>
            <th>素材组数</th>
            <th>预计项目数</th>
            <th>规则版本</th>
            <th>校验状态</th>
            <th>提交状态</th>
            <th>计划状态</th>
            <th>外部任务ID</th>
            <th>创建时间</th>
            <th class="plans-page__operations-head">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="plan in pagedPlans" :key="plan.id">
            <td class="plans-page__name">{{ plan.taskName }}</td>
            <td class="plans-page__drama">{{ plan.dramaName }}</td>
            <td>{{ plan.planType }}</td>
            <td>{{ plan.accountCount }}</td>
            <td>{{ plan.cidCount }}</td>
            <td>{{ plan.materialCount }}</td>
            <td>{{ plan.materialGroupCount }}</td>
            <td>{{ plan.expectedProjectCount }}</td>
            <td>{{ plan.ruleVersion }}</td>
            <td>{{ plan.validationStatus }}</td>
            <td>{{ plan.submitStatus }}</td>
            <td>
              <span class="plans-page__status">
                <StatusDot
                  :color="getPlanStatusMeta(plan.status).color"
                  :active="getPlanStatusMeta(plan.status).active"
                />
                {{ getPlanStatusMeta(plan.status).label }}
              </span>
            </td>
            <td class="plans-page__mono">{{ plan.externalTaskId }}</td>
            <td>{{ formatDateTime(plan.createdAt) }}</td>
            <td class="plans-page__operations">
              <button
                type="button"
                class="plans-page__action"
                @click="openPlan(plan)"
              >
                查看
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <PaginationBar
        v-model:page="page"
        v-model:page-size="pageSize"
        :total="planStore.plans.length"
      />
    </div>

    <ElDrawer
      v-model="drawerOpen"
      title="PlanSpec 预览"
      size="720px"
      destroy-on-close
    >
      <PlanSpecPreview
        :plan="selectedPlan"
        :loading="false"
        :error="null"
        @retry="load"
      />
    </ElDrawer>
  </div>
</template>

<style scoped>
.plans-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.plans-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.plans-page__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.plans-page__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}

.plans-page__scroll {
  overflow-x: auto;
}

.plans-page__table {
  width: 100%;
  min-width: 1440px;
  border-collapse: collapse;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
  font-size: var(--font-size-table);
}

.plans-page__table th {
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

.plans-page__table td {
  padding: 10px 12px;
  color: var(--color-text-primary);
  white-space: nowrap;
  border-bottom: 1px solid #f0f1f3;
}

.plans-page__table tbody tr {
  height: 48px;
  transition: background 0.15s ease;
}

.plans-page__table tbody tr:hover {
  background: var(--color-bg-panel-secondary);
}

.plans-page__table tbody tr:last-child td {
  border-bottom: none;
}

.plans-page__name {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plans-page__drama {
  max-width: 200px;
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
}

.plans-page__mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  color: var(--color-text-secondary);
}

.plans-page__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
}

.plans-page__operations {
  position: sticky;
  right: 0;
  background: var(--color-bg-panel);
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.plans-page__operations-head {
  right: 0;
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.plans-page__action {
  height: 28px;
  padding: 0 12px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-primary);
  font-size: var(--font-size-caption);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.plans-page__action:hover {
  background: var(--color-primary-50);
}
</style>
