export type TaskStatus = "pending" | "running" | "success" | "failed" | "paused" | "cancelled"

interface StatusInfo { label: string; color: string }

const STATUS_MAP: Record<TaskStatus, StatusInfo> = {
  pending:   { label: "未开始",   color: "var(--color-status-pending)" },
  running:   { label: "运行中",   color: "var(--color-status-running)" },
  success:   { label: "已完成",   color: "var(--color-status-success)" },
  failed:    { label: "失败",     color: "var(--color-status-failed)" },
  paused:    { label: "已暂停",   color: "var(--color-status-paused)" },
  cancelled: { label: "已取消",   color: "var(--color-status-pending)" }
}

export function getStatusLabel(status: TaskStatus): string {
  return STATUS_MAP[status]?.label ?? "未知"
}

export function getStatusColor(status: TaskStatus): string {
  return STATUS_MAP[status]?.color ?? "var(--color-status-pending)"
}
