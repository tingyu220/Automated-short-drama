/** 任务领域类型与展示辅助函数 */

export type WorkflowNodeStatus =
  | "done"
  | "current"
  | "pending"
  | "skipped"
  | "failed"

export interface WorkflowStepNode {
  key: string
  label: string
  status: WorkflowNodeStatus
}

export const WORKFLOW_STEPS: WorkflowStepNode[] = [
  { key: "feishu", label: "飞书", status: "pending" },
  { key: "link", label: "链接", status: "pending" },
  { key: "resource", label: "剧目资源", status: "pending" },
  { key: "config", label: "推广配置", status: "pending" },
  { key: "product", label: "产品库", status: "pending" },
  { key: "planspec", label: "PlanSpec", status: "pending" },
  { key: "submit", label: "提交", status: "pending" },
  { key: "confirm", label: "状态确认", status: "pending" }
]

export const WORKFLOW_NODE_META: Record<
  WorkflowNodeStatus,
  { label: string; color: string }
> = {
  done: { label: "已完成", color: "var(--color-status-success)" },
  current: { label: "执行中", color: "var(--color-status-running)" },
  pending: { label: "等待中", color: "var(--color-status-pending)" },
  skipped: { label: "已跳过", color: "var(--color-status-pending)" },
  failed: { label: "失败", color: "var(--color-status-failed)" }
}

export function getWorkflowNodeMeta(status: WorkflowNodeStatus): {
  label: string
  color: string
} {
  return WORKFLOW_NODE_META[status] ?? WORKFLOW_NODE_META.pending
}

export function buildWorkflowSteps(
  currentKey?: string | null,
  failedKey?: string | null
): WorkflowStepNode[] {
  const failedIndex = WORKFLOW_STEPS.findIndex((step) => step.key === failedKey)
  const currentIndex = WORKFLOW_STEPS.findIndex((step) => step.key === currentKey)
  const activeIndex = failedIndex >= 0 ? failedIndex : currentIndex
  return WORKFLOW_STEPS.map((step, index) => {
    if (failedIndex >= 0 && index === failedIndex) {
      return { ...step, status: "failed" }
    }
    if (currentIndex >= 0 && index === currentIndex) {
      return { ...step, status: "current" }
    }
    if (activeIndex >= 0 && index < activeIndex) {
      return { ...step, status: "done" }
    }
    return { ...step, status: "pending" }
  })
}

export interface TaskBase {
  id: string
  drama_name: string
  platform: string
  available_time: string
  status: string
  owner: string | null
  queue_state: string | null
  updated_at: string
}

export interface TaskView extends TaskBase {
  current_step?: string | null
  iaa?: string | null
  price_9_9?: string | null
  price_2_9?: string | null
  album_id?: string | null
  product_library?: string | null
  plan_spec?: string | null
  plan_status?: string | null
  exception_status?: string | null
}

export interface QueueItemView {
  id: string
  task_id: string
  state: string
  priority: number
  available_at: string
  claimed_by: string | null
  lease_until: string | null
  attempt_count: number
  next_run_at: string | null
}

export interface PromotionLink {
  key: "iaa" | "iap_9_9" | "iap_2_9"
  label: string
  status: string
  source: string
  entry: string
  method: string
  url: string
  selection?: string
  template?: string
  price?: string
  target_price?: string
  price_diff?: string
  extracted_at?: string
  rule_version?: string
}

export interface WorkflowRunItem {
  step: string
  status: string
  started_at?: string | null
  finished_at?: string | null
  duration_ms?: number | null
  result?: string | null
  error?: string | null
  screenshot?: string | null
}

export type TaskAction =
  | "manual_enqueue"
  | "pause"
  | "resume"
  | "retry"
  | "cancel"

export function toTaskView(
  task: TaskBase,
  extras: Partial<TaskView> = {}
): TaskView {
  return { ...task, ...extras }
}

export function maskUrl(url: string): string {
  if (!url) return ""
  if (url.length <= 32) return url
  return `${url.slice(0, 20)}…${url.slice(-12)}`
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatDuration(start?: string | null, end?: string | null): string {
  const startMs = start ? Date.parse(start) : Number.NaN
  if (Number.isNaN(startMs)) return "—"
  const endMs = end ? Date.parse(end) : Date.now()
  const diff = Math.max(0, endMs - startMs)
  const minutes = Math.floor(diff / 60000)
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
  if (minutes > 0) return `${minutes}m`
  return `${Math.max(1, Math.floor(diff / 1000))}s`
}

export function formatRemainingTime(target?: string | null): string {
  if (!target) return "—"
  const targetMs = Date.parse(target)
  if (Number.isNaN(targetMs)) return "—"
  const diff = targetMs - Date.now()
  if (diff <= 0) return "已到时间"
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时 ${minutes % 60} 分钟`
  return `${Math.floor(hours / 24)} 天`
}

const LINK_STATUS_META: Record<string, { label: string; color: string }> = {
  ready: { label: "已就绪", color: "var(--color-status-success)" },
  checking: { label: "检测中", color: "var(--color-status-running)" },
  pending: { label: "提取中", color: "var(--color-status-pending)" },
  failed: { label: "提取失败", color: "var(--color-status-failed)" }
}

export function getLinkStatusMeta(status?: string | null): {
  label: string
  color: string
} {
  if (!status) return { label: "未提取", color: "var(--color-status-pending)" }
  return (
    LINK_STATUS_META[status.toLowerCase()] ?? {
      label: status,
      color: "var(--color-status-pending)"
    }
  )
}
