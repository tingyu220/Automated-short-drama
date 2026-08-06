<script setup lang="ts">
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import { formatDateTime, formatFileSize } from "@/shared/utils/format"
import type { ExecutionArtifactView } from "@/app/stores/records"

defineProps<{
  items: ExecutionArtifactView[]
  loading: boolean
  error: string | null
}>()

defineEmits<{
  (e: "retry"): void
}>()

const TYPE_LABEL: Record<string, string> = {
  screenshot: "截图",
  file: "文件",
  log: "日志",
  export: "导出"
}

function fileName(path: string): string {
  const clean = path.split(/[\\/]/).pop() ?? path
  return clean || path
}

function typeLabel(type: string): string {
  return TYPE_LABEL[type.toLowerCase()] ?? (type || "文件")
}

function href(path: string): string {
  if (/^https?:\/\//.test(path)) return path
  return `/api/artifacts/${encodeURIComponent(path.replace(/^\/+/, ""))}`
}
</script>

<template>
  <section class="artifact-viewer">
    <ErrorState
      v-if="error"
      :message="error"
      retry-text="重新加载"
      @retry="$emit('retry')"
    />
    <LoadingSkeleton v-else-if="loading && items.length === 0" :rows="4" />
    <EmptyState
      v-else-if="items.length === 0"
      title="暂无截图与文件"
      description="任务执行产生的截图和文件会展示在这里"
    />
    <div v-else class="artifact-viewer__grid">
      <article
        v-for="artifact in items"
        :key="artifact.id"
        class="artifact-viewer__card"
      >
        <div class="artifact-viewer__head">
          <span class="artifact-viewer__type">{{ typeLabel(artifact.artifact_type) }}</span>
          <span class="artifact-viewer__size">{{ formatFileSize(artifact.size_bytes) }}</span>
        </div>
        <h3 class="artifact-viewer__name" :title="artifact.path">
          {{ fileName(artifact.path) }}
        </h3>
        <p class="artifact-viewer__meta">
          {{ formatDateTime(artifact.created_at) }} · 任务 {{ artifact.task_id }}
        </p>
        <a
          class="artifact-viewer__open"
          :href="href(artifact.path)"
          target="_blank"
          rel="noreferrer"
        >
          打开文件
        </a>
      </article>
    </div>
  </section>
</template>

<style scoped>
.artifact-viewer__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.artifact-viewer__card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-card);
}

.artifact-viewer__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.artifact-viewer__type {
  display: inline-flex;
  height: 22px;
  align-items: center;
  padding: 0 8px;
  color: var(--color-primary);
  background: var(--color-primary-50);
  border-radius: 999px;
  font-size: var(--font-size-caption);
}

.artifact-viewer__size {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.artifact-viewer__name {
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-viewer__meta {
  overflow: hidden;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-viewer__open {
  align-self: flex-start;
  margin-top: 4px;
  color: var(--color-primary);
  font-size: var(--font-size-caption);
  font-weight: 500;
}
</style>
