<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ElTable, ElTableColumn, ElTag, ElButton, ElDrawer } from "element-plus"
import PageHeader from "@/shared/ui/PageHeader.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import { useMiniprogramStore } from "@/app/stores/miniprogram"
import type { MiniProgramTask } from "@/app/stores/miniprogram"
import MiniprogramTaskDetail from "./MiniprogramTaskDetail.vue"

const store = useMiniprogramStore()
const detailVisible = ref(false)
const selectedTask = ref<MiniProgramTask | null>(null)

function statusMeta(status: string): { label: string; color: string } {
  const map: Record<string, { label: string; color: string }> = {
    NOT_STARTED: { label: "未开始", color: "var(--color-status-pending)" },
    CONTEXT_READY: { label: "上下文就绪", color: "var(--color-status-running)" },
    DISCOVERY_READY: { label: "发现就绪", color: "var(--color-status-running)" },
    READY_FOR_IMPLEMENTATION: { label: "待实施", color: "var(--color-status-success)" },
    MANUAL_REVIEW: { label: "人工审核", color: "var(--color-status-error)" },
    FAILED: { label: "失败", color: "var(--color-status-error)" },
  }
  return map[status] ?? { label: status, color: "var(--color-status-pending)" }
}

function openDetail(task: MiniProgramTask) {
  selectedTask.value = task
  detailVisible.value = true
  store.fetchDiscovery(task.task_id)
}

async function refresh() {
  await Promise.all([store.fetchTasks(), store.fetchConfigs()])
}

onMounted(() => {
  refresh()
})
</script>

<template>
  <div class="miniprogram-page">
    <PageHeader title="小程序投放" subtitle="小程序推广链接 · 商品 · 资产管理">
      <ElButton size="small" :loading="store.tasksLoading" @click="refresh">刷新</ElButton>
    </PageHeader>

    <!-- 任务列表 -->
    <section class="miniprogram-section">
      <div class="miniprogram-section__header">
        <h3 class="miniprogram-section__title">任务列表</h3>
      </div>
      <ErrorState
        v-if="store.tasksError"
        :message="store.tasksError"
        retry-text="重试"
        @retry="store.fetchTasks()"
      />
      <LoadingSkeleton v-else-if="store.tasksLoading && store.tasks.length === 0" :rows="4" />
      <EmptyState
        v-else-if="store.tasks.length === 0"
        title="暂无小程序任务"
        description="任务从剧目表同步后自动创建"
      />
      <ElTable
        v-else
        :data="store.tasks"
        stripe
        style="width: 100%"
        @row-click="openDetail"
      >
        <ElTableColumn prop="drama_name" label="剧名" min-width="180" />
        <ElTableColumn prop="operator_name" label="投手" width="80" />
        <ElTableColumn prop="organization_group" label="归属组织" width="120" />
        <ElTableColumn prop="album_id" label="专辑ID" width="120">
          <template #default="{ row }">
            <span v-if="row.album_id">{{ row.album_id }}</span>
            <span v-else style="color: var(--color-text-tertiary)">—</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="120">
          <template #default="{ row }">
            <StatusDot
              :color="statusMeta(row.workflow_status).color"
              :active="row.workflow_status === 'CONTEXT_READY' || row.workflow_status === 'DISCOVERY_READY'"
            />
            <span class="miniprogram-status-label">{{ statusMeta(row.workflow_status).label }}</span>
          </template>
        </ElTableColumn>
      </ElTable>
    </section>

    <!-- 剧场配置 -->
    <section class="miniprogram-section">
      <div class="miniprogram-section__header">
        <h3 class="miniprogram-section__title">剧场配置</h3>
      </div>
      <ErrorState
        v-if="store.configsError"
        :message="store.configsError"
        retry-text="重试"
        @retry="store.fetchConfigs()"
      />
      <LoadingSkeleton v-else-if="store.configsLoading && store.configs.length === 0" :rows="2" />
      <EmptyState
        v-else-if="store.configs.length === 0"
        title="暂无配置"
        description="在 backend/miniprogram/configs/ 下添加 YAML"
      />
      <div v-else class="miniprogram-configs">
        <div
          v-for="cfg in store.configs"
          :key="cfg.config_name"
          class="miniprogram-config-card"
        >
          <div class="miniprogram-config-card__header">
            <span class="miniprogram-config-card__name">{{ cfg.mini_program.name }}</span>
            <ElTag size="small">{{ cfg.config_name }}</ElTag>
          </div>
          <div class="miniprogram-config-card__body">
            <div class="miniprogram-config-row">
              <span class="miniprogram-config-label">AppID</span>
              <code>{{ cfg.mini_program.app_id }}</code>
            </div>
            <div class="miniprogram-config-row">
              <span class="miniprogram-config-label">原始ID</span>
              <code>{{ cfg.mini_program.original_id }}</code>
            </div>
            <div class="miniprogram-config-row">
              <span class="miniprogram-config-label">收费类型</span>
              <span>{{ cfg.promotion.charge_type }}</span>
            </div>
            <div class="miniprogram-config-row">
              <span class="miniprogram-config-label">价格档位</span>
              <div class="miniprogram-config-tiers">
                <ElTag
                  v-for="(tierCfg, tier) in cfg.price_tiers"
                  :key="tier"
                  size="small"
                  type="success"
                >
                  {{ tier }} — {{ tierCfg.product_library }}
                </ElTag>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Task Detail Drawer -->
    <ElDrawer
      v-model="detailVisible"
      :title="selectedTask ? `任务详情 · ${selectedTask.drama_name}` : '任务详情'"
      direction="rtl"
      size="640px"
    >
      <MiniprogramTaskDetail
        v-if="selectedTask"
        :task="selectedTask"
        :discovery="store.discovery"
        :loading="store.discoveryLoading"
      />
    </ElDrawer>
  </div>
</template>

<style scoped>
.miniprogram-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.miniprogram-section {
  margin-bottom: 32px;
}

.miniprogram-section__header {
  margin-bottom: 16px;
}

.miniprogram-section__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.miniprogram-status-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-left: 6px;
}

.miniprogram-configs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.miniprogram-config-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-card, 12px);
  border: 1px solid var(--color-border-light, #e5e7eb);
  padding: 20px;
}

.miniprogram-config-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.miniprogram-config-card__name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.miniprogram-config-card__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.miniprogram-config-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.miniprogram-config-label {
  color: var(--color-text-tertiary);
  min-width: 80px;
}

.miniprogram-config-row code {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  color: var(--color-text-primary);
  background: var(--color-bg-muted, #f8fafc);
  padding: 2px 6px;
  border-radius: 4px;
}

.miniprogram-config-tiers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
