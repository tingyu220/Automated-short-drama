export interface PlanStatusMeta {
  label: string
  color: string
  active: boolean
}

const PLAN_STATUS_MAP: Record<string, PlanStatusMeta> = {
  draft: { label: "草稿", color: "var(--color-status-pending)", active: false },
  validating: { label: "待校验", color: "var(--color-status-running)", active: true },
  pending_validation: { label: "待校验", color: "var(--color-status-running)", active: true },
  validation_failed: { label: "校验失败", color: "var(--color-status-failed)", active: false },
  failed: { label: "校验失败", color: "var(--color-status-failed)", active: false },
  ready: { label: "可执行", color: "var(--color-status-success)", active: false },
  validated: { label: "可执行", color: "var(--color-status-success)", active: false },
  executable: { label: "可执行", color: "var(--color-status-success)", active: false },
  submitting: { label: "提交中", color: "var(--color-status-running)", active: true },
  submitted: { label: "提交中", color: "var(--color-status-running)", active: true },
  result_uncertain: { label: "结果不确定", color: "var(--color-status-warning)", active: false },
  uncertain: { label: "结果不确定", color: "var(--color-status-warning)", active: false },
  completed: { label: "已完成", color: "var(--color-status-success)", active: false },
  success: { label: "已完成", color: "var(--color-status-success)", active: false }
}

export function getPlanStatusMeta(status?: string | null): PlanStatusMeta {
  if (!status) {
    return { label: "未知", color: "var(--color-status-pending)", active: false }
  }
  return (
    PLAN_STATUS_MAP[status.trim().toLowerCase()] ?? {
      label: status,
      color: "var(--color-status-pending)",
      active: false
    }
  )
}
