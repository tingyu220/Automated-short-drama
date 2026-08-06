<script setup lang="ts">
import { computed, onMounted } from "vue"
import { ElButton } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import ArtifactViewer from "@/widgets/artifact-viewer/ArtifactViewer.vue"
import { useRecordsStore } from "@/app/stores/records"
import { getStatusColor, getStatusLabel } from "@/shared/utils/status"
import { formatDateTime, formatFileSize } from "@/shared/utils/format"

const recordsStore = useRecordsStore()

const ACTIVE_TAB = "ledger"
const TAB_LABELS = [
  { key: "ledger", label: "业务台账" },
  { key: "workflow", label: "工作流运行" },
  { key: "steps", label: "步骤记录" },
  { key: "audit", label: "操作审计" },
  { key: "config", label: "配置变更" },
  { key: "artifacts", label: "截图与文件" },
  { key: "cleanup", label: "资源清理" }
]

const hasData = computed(
  () =>
    recordsStore.ledgers.length > 0 ||
    recordsStore.events.length > 0 ||
    recordsStore.artifacts.length > 0
)

const cleanupItems = computed(() =>
  recordsStore.artifacts.filter(
    (artifact) =>
      artifact.artifact_type.toLowerCase().includes("cleanup") ||
      artifact.artifact_type.toLowerCase().includes("delete")
  )
)

async function load() {
  await recordsStore.fetchRecords()
}

onMounted(load)

function levelColor(level: string): string {
  const normalized = level.toLowerCase()
  if (normalized.includes("error")) return "var(--color-status-failed)"
  if (normalized.includes("warn")) return "var(--color-status-warning)"
  return "var(--color-status-running)"
}
</script>

<template>
  <div class="records-page">
    <header class="records-page__header">
      <div>
        <h1 class="records-page__title">系统记录</h1>
        <p class="records-page__subtitle">
          业务台账、工作流运行、操作审计、配置变更与执行产物
        </p>
      </div>
      <ElButton :loading="recordsStore.loading" @click="load">
        <el-icon><Refresh /></el-icon>
        刷新
      </ElButton>
    </header>

    <ErrorState
      v-if="recordsStore.error"
      :message="recordsStore.error"
      retry-text="重新加载"
      @retry="load"
    />
    <LoadingSkeleton
      v-else-if="recordsStore.loading && !hasData"
      :rows="6"
    />
    <EmptyState
      v-else-if="!hasData"
      title="暂无系统记录"
      description="任务执行后会自动产生台账、事件、截图与文件记录"
    />
    <div v-else class="records-page__panel">
      <el-tabs :model-value="ACTIVE_TAB" class="records-page__tabs">
        <el-tab-pane
          v-for="tab in TAB_LABELS"
          :key="tab.key"
          :label="tab.label"
          :name="tab.key"
        >
          <div v-if="tab.key === 'ledger'" class="records-page__scroll">
            <EmptyState
              v-if="recordsStore.ledgers.length === 0"
              title="暂无台账"
              description="任务完成后会在此保留最小业务台账"
            />
            <table v-else class="records-page__table">
              <thead>
                <tr>
                  <th>剧名</th>
                  <th>飞书行</th>
                  <th>专辑ID</th>
                  <th>产品ID</th>
                  <th>外部任务ID</th>
                  <th>任务名称</th>
                  <th>最终状态</th>
                  <th>规则版本</th>
                  <th>配置版本</th>
                  <th>完成时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ledger in recordsStore.ledgers" :key="ledger.id">
                  <td class="records-page__strong">{{ ledger.dramaName }}</td>
                  <td>{{ ledger.feishuRow }}</td>
                  <td class="records-page__mono">{{ ledger.albumId }}</td>
                  <td class="records-page__mono">{{ ledger.productId }}</td>
                  <td class="records-page__mono">{{ ledger.externalTaskId }}</td>
                  <td class="records-page__name" :title="ledger.taskName">
                    {{ ledger.taskName }}
                  </td>
                  <td>
                    <span class="records-page__status">
                      <StatusDot
                        :color="getStatusColor(ledger.finalStatus)"
                      />
                      {{ getStatusLabel(ledger.finalStatus) }}
                    </span>
                  </td>
                  <td>{{ ledger.ruleVersion }}</td>
                  <td>{{ ledger.configVersion }}</td>
                  <td>{{ ledger.completedAt }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-else-if="tab.key === 'workflow' || tab.key === 'steps'"
            class="records-page__scroll"
          >
            <EmptyState
              v-if="recordsStore.events.length === 0"
              title="暂无执行记录"
              description="工作流事件会按发生顺序记录在这里"
            />
            <table v-else class="records-page__table records-page__table--events">
              <thead>
                <tr>
                  <th>发生时间</th>
                  <th>任务ID</th>
                  <th v-if="tab.key === 'steps'">步骤</th>
                  <th>事件类型</th>
                  <th>级别</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="event in recordsStore.events" :key="event.id">
                  <td>{{ formatDateTime(event.occurred_at) }}</td>
                  <td class="records-page__mono">{{ event.task_id }}</td>
                  <td v-if="tab.key === 'steps'">
                    {{
                      event.context_json?.step_name ||
                      event.context_json?.step ||
                      "—"
                    }}
                  </td>
                  <td>{{ event.event_type }}</td>
                  <td>
                    <span class="records-page__status">
                      <StatusDot :color="levelColor(event.level)" />
                      {{ event.level }}
                    </span>
                  </td>
                  <td class="records-page__message" :title="event.message">
                    {{ event.message }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-else-if="tab.key === 'artifacts'">
            <ArtifactViewer
              :items="recordsStore.artifacts"
              :loading="recordsStore.loading"
              :error="recordsStore.error"
              @retry="load"
            />
          </div>

          <EmptyState
            v-else-if="tab.key === 'audit'"
            title="暂无操作审计"
            description="规则发布、配置变更等操作记录将在此展示"
          />
          <EmptyState
            v-else-if="tab.key === 'config'"
            title="暂无配置变更"
            description="配置版本与变更差异将在此展示"
          />
          <EmptyState
            v-else-if="cleanupItems.length === 0"
            title="暂无资源清理记录"
            description="过期截图与临时文件清理记录将在此展示"
          />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
.records-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.records-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.records-page__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.records-page__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}

.records-page__panel {
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.records-page__scroll {
  overflow-x: auto;
}

.records-page__table {
  width: 100%;
  min-width: 1280px;
  border-collapse: collapse;
  font-size: var(--font-size-table);
}

.records-page__table--events {
  min-width: 860px;
}

.records-page__table th {
  padding: 10px 12px;
  background: var(--color-bg-panel-secondary);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #e5e7eb;
}

.records-page__table td {
  max-width: 240px;
  padding: 10px 12px;
  overflow: hidden;
  color: var(--color-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
  border-bottom: 1px solid #f0f1f3;
}

.records-page__table tbody tr {
  height: 48px;
  transition: background 0.15s ease;
}

.records-page__table tbody tr:hover {
  background: var(--color-bg-panel-secondary);
}

.records-page__table tbody tr:last-child td {
  border-bottom: none;
}

.records-page__strong {
  font-weight: 500;
}

.records-page__mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  color: var(--color-text-secondary);
}

.records-page__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
}

.records-page__message {
  color: var(--color-text-secondary);
}

:deep(.records-page__tabs .el-tabs__item) {
  height: 36px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
}

:deep(.records-page__tabs .el-tabs__item.is-active) {
  color: var(--color-primary);
}

:deep(.records-page__tabs .el-tabs__active-bar) {
  background-color: var(--color-primary);
}
</style>
