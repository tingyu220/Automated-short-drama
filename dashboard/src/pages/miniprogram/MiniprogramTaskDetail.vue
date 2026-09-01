<script setup lang="ts">
import { ElTag, ElCollapse, ElCollapseItem } from "element-plus"
import StatusDot from "@/shared/ui/StatusDot.vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import type {
  MiniProgramTask,
  MiniProgramDiscovery,
} from "@/app/stores/miniprogram"

const props = defineProps<{
  task: MiniProgramTask
  discovery: MiniProgramDiscovery | null
  loading?: boolean
}>()

function statusMeta(status: string): { label: string; color: string; active: boolean } {
  const map: Record<string, { label: string; color: string; active: boolean }> = {
    NOT_STARTED: { label: "未开始", color: "var(--color-status-pending)", active: false },
    CONTEXT_READY: { label: "上下文就绪", color: "var(--color-status-running)", active: true },
    DISCOVERY_READY: { label: "发现就绪", color: "var(--color-status-running)", active: true },
    READY_FOR_IMPLEMENTATION: { label: "待实施", color: "var(--color-status-success)", active: false },
    MANUAL_REVIEW: { label: "人工审核", color: "var(--color-status-error)", active: false },
    FAILED: { label: "失败", color: "var(--color-status-error)", active: false },
  }
  return map[status] ?? { label: status, color: "var(--color-status-pending)", active: false }
}

function formatBody(body: unknown): string {
  return JSON.stringify(body, null, 2)
}
</script>

<template>
  <div class="mp-detail">
    <!-- Drama Context -->
    <div class="mp-detail__section">
      <h4 class="mp-detail__section-title">Drama Context</h4>
      <div class="mp-detail__grid">
        <div class="mp-detail__row">
          <span class="mp-detail__label">剧名</span>
          <span class="mp-detail__value">{{ task.drama_name }}</span>
        </div>
        <div class="mp-detail__row">
          <span class="mp-detail__label">简称</span>
          <span class="mp-detail__value">{{ task.drama_short_name || '—' }}</span>
        </div>
        <div class="mp-detail__row">
          <span class="mp-detail__label">album_id</span>
          <code v-if="task.album_id">{{ task.album_id }}</code>
          <span v-else style="color: var(--color-text-tertiary)">未关联</span>
        </div>
      </div>
    </div>

    <!-- Operator & Organization -->
    <div class="mp-detail__section">
      <h4 class="mp-detail__section-title">Operator & Organization</h4>
      <div class="mp-detail__grid">
        <div class="mp-detail__row">
          <span class="mp-detail__label">投手</span>
          <span class="mp-detail__value">{{ task.operator_name }} ({{ task.operator_code }})</span>
        </div>
        <div class="mp-detail__row">
          <span class="mp-detail__label">归属组织</span>
          <span class="mp-detail__value">{{ task.organization_group }}</span>
        </div>
        <div class="mp-detail__row">
          <span class="mp-detail__label">组织路径</span>
          <span class="mp-detail__value">{{ task.organization_path }}</span>
        </div>
      </div>
    </div>

    <!-- Workflow State -->
    <div class="mp-detail__section">
      <h4 class="mp-detail__section-title">Workflow State</h4>
      <div class="mp-detail__row">
        <StatusDot
          :color="statusMeta(task.workflow_status).color"
          :active="statusMeta(task.workflow_status).active"
        />
        <span class="mp-detail__status-label">{{ statusMeta(task.workflow_status).label }}</span>
        <ElTag size="small" type="info" style="margin-left: auto">
          {{ task.workflow_status }}
        </ElTag>
      </div>
    </div>

    <!-- Network Discovery Result -->
    <div class="mp-detail__section">
      <h4 class="mp-detail__section-title">Network Discovery</h4>
      <LoadingSkeleton v-if="props.loading && !props.discovery" :rows="2" />
      <EmptyState
        v-else-if="!props.discovery"
        title="暂无 Discovery 数据"
        description="M0 阶段需人工操作页面触发接口"
      />
      <div v-else class="mp-discovery">
        <div class="mp-discovery__summary">
          <ElTag size="small" type="success">
            捕获 {{ props.discovery.capture_count }} 条
          </ElTag>
          <ElTag
            v-for="et in props.discovery.endpoint_types"
            :key="et"
            size="small"
            type="info"
          >
            {{ et }} ({{ props.discovery.endpoint_counts[et] }})
          </ElTag>
        </div>

        <ElCollapse>
          <ElCollapseItem
            v-for="(cap, idx) in props.discovery.captures"
            :key="idx"
            :name="String(idx)"
          >
            <template #title>
              <span class="mp-discovery__capture-title">
                <ElTag size="small" type="info">{{ cap.method }}</ElTag>
                <span class="mp-discovery__capture-url">{{ cap.url.substring(0, 80) }}{{ cap.url.length > 80 ? '...' : '' }}</span>
                <ElTag size="small" :type="cap.status < 300 ? 'success' : 'warning'">{{ cap.status }}</ElTag>
                <ElTag size="small">{{ cap.endpoint_type }}</ElTag>
              </span>
            </template>
            <pre class="mp-discovery__body">{{ formatBody(cap.response_body) }}</pre>
          </ElCollapseItem>
        </ElCollapse>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mp-detail {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.mp-detail__section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mp-detail__section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
}

.mp-detail__grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mp-detail__row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.mp-detail__label {
  color: var(--color-text-tertiary);
  min-width: 80px;
}

.mp-detail__value {
  color: var(--color-text-primary);
}

.mp-detail__status-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin-left: 6px;
}

.mp-discovery__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.mp-discovery__capture-title {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
}

.mp-discovery__capture-url {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  color: var(--color-text-secondary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mp-discovery__body {
  margin: 0;
  padding: 12px;
  background: var(--color-bg-muted, #f8fafc);
  border-radius: 8px;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow: auto;
}
</style>
