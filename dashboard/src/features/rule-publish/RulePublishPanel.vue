<script setup lang="ts">
import { ref } from "vue"
import { ElButton, ElDialog, ElMessage } from "element-plus"
import ConfirmActionDialog from "@/shared/ui/ConfirmActionDialog.vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import { formatDateTime } from "@/entities/task/types"
import { useRuleStore } from "@/app/stores/rule"
import type { RuleVersion, RuleVersionDetail } from "@/app/stores/rule"

const props = defineProps<{
  ruleSetId: string | null
  ruleSetName?: string
  versions: RuleVersion[]
  loading?: boolean
  error?: string | null
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: "validate", ruleSetId: string): void
  (e: "publish", ruleSetId: string): void
  (e: "delete", ruleSetId: string, versionId: string): void
  (e: "retry"): void
}>()

const ruleStore = useRuleStore()

const confirmVisible = ref(false)
const deleteConfirmVisible = ref(false)
const deleteTargetId = ref<string | null>(null)
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref<RuleVersionDetail | null>(null)

function versionStatusMeta(status: string): {
  label: string
  color: string
  active: boolean
} {
  const map: Record<string, { label: string; color: string; active: boolean }> = {
    DRAFT: { label: "草稿", color: "var(--color-status-pending)", active: false },
    VALIDATING: {
      label: "校验中",
      color: "var(--color-status-running)",
      active: true
    },
    PUBLISHED: {
      label: "已发布",
      color: "var(--color-status-success)",
      active: false
    },
    ARCHIVED: {
      label: "已归档",
      color: "var(--color-status-pending)",
      active: false
    }
  }
  return map[status] ?? { label: status, color: "var(--color-status-pending)", active: false }
}

function onValidate() {
  if (props.ruleSetId) emit("validate", props.ruleSetId)
}

function onPublish() {
  if (props.ruleSetId) {
    confirmVisible.value = true
  }
}

function confirmPublish() {
  confirmVisible.value = false
  if (props.ruleSetId) emit("publish", props.ruleSetId)
}

function onDelete(versionId: string) {
  deleteTargetId.value = versionId
  deleteConfirmVisible.value = true
}

function confirmDelete() {
  deleteConfirmVisible.value = false
  const versionId = deleteTargetId.value
  deleteTargetId.value = null
  if (props.ruleSetId && versionId) emit("delete", props.ruleSetId, versionId)
}

async function onView(versionId: string) {
  if (!props.ruleSetId) return
  detailLoading.value = true
  detailData.value = null
  detailVisible.value = true
  try {
    const detail = await ruleStore.fetchVersionDetail(props.ruleSetId, versionId)
    if (detail) {
      detailData.value = detail
    } else if (ruleStore.error) {
      ElMessage.error(ruleStore.error)
      detailVisible.value = false
    }
  } finally {
    detailLoading.value = false
  }
}

function formatPayload(payload: Record<string, unknown>): string {
  return JSON.stringify(payload, null, 2)
}
</script>

<template>
  <section class="rule-publish" aria-label="版本管理">
    <header class="rule-publish__header">
      <div>
        <h2 class="rule-publish__title">
          版本管理<span v-if="ruleSetName" class="rule-publish__rule-name"> · {{ ruleSetName }}</span>
        </h2>
        <p class="rule-publish__hint">
          发布后新任务使用新版本，运行中任务继续使用配置快照。
        </p>
      </div>
      <div class="rule-publish__actions">
        <ElButton
          size="small"
          :disabled="!ruleSetId"
          :loading="busy"
          @click="onValidate"
        >
          校验
        </ElButton>
        <ElButton
          size="small"
          type="primary"
          :disabled="!ruleSetId"
          :loading="busy"
          @click="onPublish"
        >
          发布
        </ElButton>
      </div>
    </header>

    <ErrorState
      v-if="error"
      :message="error"
      retry-text="重新加载"
      @retry="emit('retry')"
    />
    <LoadingSkeleton v-else-if="loading && versions.length === 0" :rows="3" />
    <EmptyState
      v-else-if="versions.length === 0"
      title="暂无版本"
      :description="ruleSetId ? '保存草稿并校验后生成版本' : '当前分类暂无规则集'"
    />
    <ul v-else class="rule-publish__list">
      <li
        v-for="version in versions"
        :key="version.id"
        class="rule-publish__item"
      >
        <div class="rule-publish__item-main">
          <span class="rule-publish__version">
            <span v-if="ruleSetName" class="rule-publish__version-name">{{ ruleSetName }}</span>
            v{{ version.version }}
          </span>
          <span class="rule-publish__status">
            <StatusDot
              :color="versionStatusMeta(version.status).color"
              :active="versionStatusMeta(version.status).active"
            />
            {{ versionStatusMeta(version.status).label }}
          </span>
        </div>
        <div class="rule-publish__item-right">
          <span class="rule-publish__item-meta">{{ formatDateTime(version.published_at) }}</span>
          <ElButton
            size="small"
            type="text"
            :disabled="busy"
            @click="onView(version.id)"
          >
            查看
          </ElButton>
          <ElButton
            size="small"
            type="text"
            text-color="#ff4d4f"
            :disabled="busy"
            @click="onDelete(version.id)"
          >
            删除
          </ElButton>
        </div>
      </li>
    </ul>

    <ConfirmActionDialog
      v-model="confirmVisible"
      title="发布规则版本"
      content="发布后，新任务将使用该版本规则；运行中任务继续使用已生成的配置快照。请确认影响范围后再发布。"
      confirm-text="确认发布"
      @confirm="confirmPublish"
    />
    <ConfirmActionDialog
      v-model="deleteConfirmVisible"
      title="删除版本"
      content="删除后该版本将无法恢复，请确认是否继续。"
      confirm-text="确认删除"
      confirm-type="danger"
      @confirm="confirmDelete"
    />
    <ElDialog
      v-model="detailVisible"
      :title="detailData ? `版本 v${detailData.version} 详情` : '版本详情'"
      width="680px"
      :close-on-click-modal="false"
    >
      <div v-if="detailLoading" class="rule-publish__detail-loading">
        加载中...
      </div>
      <div v-else-if="detailData" class="rule-publish__detail">
        <div class="rule-publish__detail-header">
          <span class="rule-publish__detail-status">
            <StatusDot
              :color="versionStatusMeta(detailData.status).color"
              :active="versionStatusMeta(detailData.status).active"
            />
            {{ versionStatusMeta(detailData.status).label }}
          </span>
          <span class="rule-publish__detail-time">
            {{ formatDateTime(detailData.published_at) }}
          </span>
        </div>
        <pre class="rule-publish__detail-payload">{{ formatPayload(detailData.payload_json) }}</pre>
      </div>
      <template #footer>
        <ElButton @click="detailVisible = false">关闭</ElButton>
      </template>
    </ElDialog>
  </section>
</template>

<style scoped>
.rule-publish {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.rule-publish__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.rule-publish__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.rule-publish__rule-name {
  color: var(--color-primary-600);
}

.rule-publish__hint {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-publish__actions {
  display: flex;
  gap: 8px;
  flex: none;
}

.rule-publish__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
}

.rule-publish__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
}

.rule-publish__item-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rule-publish__version {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  color: var(--color-text-primary);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-body);
  font-weight: 600;
}

.rule-publish__version-name {
  color: var(--color-text-secondary);
  font-family: var(--font-family);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.rule-publish__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.rule-publish__item-meta {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-publish__item-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.rule-publish__detail-loading {
  padding: 40px 0;
  text-align: center;
  color: var(--color-text-tertiary);
}

.rule-publish__detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.rule-publish__detail-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
}

.rule-publish__detail-time {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-publish__detail-payload {
  margin: 0;
  padding: 16px;
  max-height: 480px;
  overflow: auto;
  background: #f8fafc;
  border-radius: var(--radius-card);
  color: var(--color-text-primary);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
