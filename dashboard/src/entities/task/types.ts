/** 任务领域类型与展示辅助函数 */

import {
  formatDateTime,
  formatDuration,
  formatRemainingTime,
  parseDateTimeUtc
} from "@/shared/utils/format"

export { formatDateTime, formatDuration, formatRemainingTime }

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

export type LinkReadinessStageStatus = "done" | "current" | "pending" | "failed"

export interface LinkReadinessStageNode {
  key: string
  label: string
  detail: string
  status: LinkReadinessStageStatus
}

export const LINK_READINESS_STAGES: Omit<
  LinkReadinessStageNode,
  "status"
>[] = [
  {
    key: "WAITING_AVAILABLE_TIME",
    label: "等待上线时间",
    detail: "到点后开始处理"
  },
  {
    key: "LINK_EXTRACTION",
    label: "提取链接",
    detail: "搜索、复用或创建链接"
  },
  {
    key: "DELIVERY_DRAMA",
    label: "搭建投放剧目",
    detail: "复用或创建剧目资源"
  },
  {
    key: "PROMOTION_CONFIG",
    label: "搭建推广内容",
    detail: "按链接复用或创建配置"
  },
  {
    key: "LINK_READY",
    label: "链接已就绪",
    detail: "可以直接上剧"
  }
]

const LINK_READINESS_STAGE_INDEX = new Map(
  LINK_READINESS_STAGES.map((stage, index) => [stage.key, index])
)

export function getLinkExtractionLabel(platform?: string | null): string {
  const p = (platform ?? "").toUpperCase()
  if (p === "TOMATO") return "提取番茄链接"
  if (p === "JUBIAN") return "读取剧变链接"
  return "提取链接"
}

export function buildLinkReadinessStages(
  currentStage?: string | null,
  taskStatus?: string | null,
  steps: Array<Pick<LinkStageRun, "step_name" | "status">> = [],
  platform?: string | null
): LinkReadinessStageNode[] {
  const currentKey = currentStage?.toUpperCase() ?? ""
  const normalizedStatus = taskStatus?.toUpperCase() ?? ""
  const extractedOnly = normalizedStatus === "LINK_EXTRACTED"
  const terminal =
    currentKey === "LINK_READY" ||
    normalizedStatus === "LINK_READY" ||
    normalizedStatus === "COMPLETED"
  const failedStep = steps.find((step) =>
    ["FAILED", "ERROR", "MANUAL_REVIEW"].includes(step.status.toUpperCase())
  )
  const failedKey = failedStep?.step_name?.toUpperCase() ?? ""
  const activeKey = extractedOnly ? "LINK_EXTRACTION" : currentKey
  const activeIndex = LINK_READINESS_STAGE_INDEX.get(activeKey) ?? -1
  const failedIndex = LINK_READINESS_STAGE_INDEX.get(failedKey) ?? -1

  return LINK_READINESS_STAGES.map((stage, index) => {
    let status: LinkReadinessStageStatus = "pending"
    if (terminal || (extractedOnly && index <= 1)) {
      status = "done"
    } else if (failedIndex === index || (normalizedStatus === "FAILED" || normalizedStatus === "MANUAL_REVIEW") && activeIndex === index) {
      status = "failed"
    } else if (index < activeIndex) {
      status = "done"
    } else if (index === activeIndex && activeIndex >= 0) {
      status = "current"
    }
    const label = stage.key === "LINK_EXTRACTION"
      ? getLinkExtractionLabel(platform)
      : stage.label
    return { ...stage, label, status }
  })
}

export function getLinkReadinessStageLabel(
  currentStage?: string | null,
  taskStatus?: string | null,
  platform?: string | null
): string {
  const normalizedStatus = taskStatus?.toUpperCase() ?? ""
  if (normalizedStatus === "LINK_EXTRACTED") return "链接已提取"
  if (normalizedStatus === "COMPLETED") return "链接已就绪"
  const normalizedStage = currentStage?.toUpperCase() ?? ""
  const stage = LINK_READINESS_STAGES.find((s) => s.key === normalizedStage)
  if (!stage) return "未开始"
  if (stage.key === "LINK_EXTRACTION") return getLinkExtractionLabel(platform)
  return stage.label
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
  end_type: string
  available_time: string
  status: string
  owner: string | null
  queue_state: string | null
  current_stage?: string | null
  target_stage?: string | null
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
  link_set?: Record<string, string>
  delivery_drama_id?: string | null
  promotion_configs?: Record<string, string>
  steps?: LinkStageRun[]
  failure_code?: string | null
  drama_match_candidates?: Array<Record<string, unknown>>
  confirmed_drama_match?: Record<string, string> | null
}

export interface QueueItemView {
  id: string
  task_id: string
  drama_name?: string | null
  state: string
  priority: number
  available_at: string
  claimed_by: string | null
  lease_until: string | null
  attempt_count: number
  next_run_at: string | null
  failure_code: string | null
  retry_safe: boolean
  created_at?: string | null
  updated_at?: string | null
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

export interface LinkStageRun {
  step_name: string
  status: string
  started_at?: string | null
  finished_at?: string | null
  result_json?: Record<string, unknown> | null
  error_code?: string | null
  error_message?: string | null
}

export type TaskAction =
  | "manual_enqueue"
  | "pause"
  | "resume"
  | "retry"
  | "cancel"
  | "delete"

export function toTaskView(
  task: TaskBase,
  extras: Partial<TaskView> = {}
): TaskView {
  return { ...task, ...extras }
}

export function maskUrl(url: string): string {
  if (!url) return ""
  if (url.length <= 20) return url
  const head = 20
  const tail = Math.min(12, url.length - head)
  return `${url.slice(0, head)}…${url.slice(-tail)}`
}

const QUEUE_STATE_STEP_MAP: Record<string, string> = {
  QUEUED: "feishu",
  CLAIMED: "resource",
  RUNNING: "config"
}

export function queueStateToStep(state?: string | null): string | null {
  if (!state) return null
  return QUEUE_STATE_STEP_MAP[state.toUpperCase()] ?? null
}

export function parseTaskTime(value?: string | null): Date | null {
  return parseDateTimeUtc(value)
}

export function isLeaseActive(item?: {
  lease_until?: string | null
  state?: string | null
} | null): boolean {
  if (!item) return false
  if (item.state !== "RUNNING" && item.state !== "CLAIMED") return false
  if (!item.lease_until) return false
  const leaseEnd = parseDateTimeUtc(item.lease_until)
  return leaseEnd !== null && leaseEnd.getTime() > Date.now()
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
