<script setup lang="ts">
import { computed } from "vue"
import StatusDot from "./StatusDot.vue"
import { getStatusLabel, type TaskStatus } from "@/shared/utils/status"

export type BadgeType =
  | "success"
  | "running"
  | "warning"
  | "failed"
  | "paused"
  | "pending"

const props = defineProps<{
  status?: string
  text?: string
  type?: BadgeType
}>()

const TYPE_META: Record<BadgeType, { color: string; className: string }> = {
  success: { color: "var(--color-status-success)", className: "badge-success" },
  running: { color: "var(--color-status-running)", className: "badge-running" },
  warning: { color: "var(--color-status-warning)", className: "badge-warning" },
  failed: { color: "var(--color-status-failed)", className: "badge-failed" },
  paused: { color: "var(--color-status-paused)", className: "badge-paused" },
  pending: { color: "var(--color-status-pending)", className: "badge-pending" }
}

const STATUS_TO_TYPE: Record<string, BadgeType> = {
  success: "success",
  completed: "success",
  running: "running",
  queued: "running",
  claimed: "running",
  ready: "running",
  warning: "warning",
  manual_review: "warning",
  failed: "failed",
  paused: "paused",
  pending: "pending",
  waiting_time: "pending"
}

const resolvedType = computed<BadgeType>(
  () =>
    props.type ??
    STATUS_TO_TYPE[props.status?.toLowerCase() ?? ""] ??
    "pending"
)

const meta = computed(() => TYPE_META[resolvedType.value])

const displayText = computed(() => {
  if (props.text) return props.text
  return props.status ? getStatusLabel(props.status as TaskStatus) : "未知"
})
</script>

<template>
  <span class="status-badge" :class="meta.className">
    <StatusDot :color="meta.color" :active="resolvedType === 'running'" />
    <span class="status-badge__text">{{ displayText }}</span>
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: var(--font-size-caption);
  font-weight: 500;
  line-height: 1;
}

.badge-success {
  color: var(--color-status-success);
  background: color-mix(in srgb, var(--color-status-success) 12%, transparent);
}

.badge-running {
  color: var(--color-status-running);
  background: color-mix(in srgb, var(--color-status-running) 12%, transparent);
}

.badge-warning {
  color: var(--color-status-warning);
  background: color-mix(in srgb, var(--color-status-warning) 12%, transparent);
}

.badge-failed {
  color: var(--color-status-failed);
  background: color-mix(in srgb, var(--color-status-failed) 12%, transparent);
}

.badge-paused {
  color: var(--color-status-paused);
  background: color-mix(in srgb, var(--color-status-paused) 12%, transparent);
}

.badge-pending {
  color: var(--color-status-pending);
  background: color-mix(in srgb, var(--color-status-pending) 12%, transparent);
}
</style>
