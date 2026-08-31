export type TaskStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "paused"
  | "cancelled"

interface StatusInfo { label: string; color: string }

const STATUS_MAP: Record<string, StatusInfo> = {
  waiting_time: { label: "等待时间", color: "var(--color-status-pending)" },
  ready: { label: "准备完成", color: "var(--color-status-pending)" },
  link_extracted: { label: "链接已提取", color: "var(--color-status-success)" },
  link_ready: { label: "链接已就绪", color: "var(--color-status-success)" },
  queued: { label: "排队中", color: "var(--color-status-running)" },
  claimed: { label: "执行中", color: "var(--color-status-running)" },
  running: { label: "运行中", color: "var(--color-status-running)" },
  retry_wait: { label: "重试等待", color: "var(--color-status-warning)" },
  paused: { label: "已暂停", color: "var(--color-status-paused)" },
  manual_review: { label: "人工处理", color: "var(--color-status-warning)" },
  failed: { label: "失败", color: "var(--color-status-failed)" },
  completed: { label: "计划已完成", color: "var(--color-status-success)" },
  dry_run: { label: "演练完成", color: "var(--color-status-warning)" },
  cancelled: { label: "已取消", color: "var(--color-status-pending)" },
  pending: { label: "未开始", color: "var(--color-status-pending)" },
  success: { label: "已完成", color: "var(--color-status-success)" }
}

function normalizeStatus(status: string): string {
  return status.trim().toLowerCase()
}

export function getStatusLabel(status: string): string {
  return STATUS_MAP[normalizeStatus(status) as TaskStatus]?.label ?? "未知"
}

export function getStatusColor(status: string): string {
  return (
    STATUS_MAP[normalizeStatus(status) as TaskStatus]?.color ??
    "var(--color-status-pending)"
  )
}

const PLATFORM_LABEL_MAP: Record<string, string> = {
  tomato: "番茄",
  jubian: "剧变",
  feishu: "飞书",
  delivery: "投放系统",
  ocean: "巨量"
}

export function getPlatformLabel(platform?: string | null): string {
  if (!platform) return "—"
  return PLATFORM_LABEL_MAP[platform.trim().toLowerCase()] ?? platform
}
