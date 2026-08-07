/** 通用展示格式化：日期、文件大小、异常分类、台账字段。 */

export function parseDateTimeUtc(value?: string | null): Date | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  const hasTimezone =
    /[zZ]$/.test(trimmed) || /[+-]\d{2}:?\d{2}$/.test(trimmed)
  const normalized = hasTimezone
    ? trimmed
    : `${trimmed.includes("T") ? trimmed : trimmed.replace(" ", "T")}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

export type ExceptionCategoryKey =
  | "login_required"
  | "config_missing"
  | "manual_review"
  | "auto_retry"
  | "page_changed"
  | "result_uncertain"
  | "account_structure"
  | "feishu_partial_write"

export type RiskLevel = "high" | "medium" | "low"

export interface ExceptionCategoryMeta {
  key: ExceptionCategoryKey
  label: string
  risk: RiskLevel
  risk_label: string
  risk_color: string
  judgment: string
  suggested_steps: string[]
}

export interface RiskMeta {
  label: string
  color: string
}

const RISK_META: Record<RiskLevel, RiskMeta> = {
  high: { label: "高风险", color: "var(--color-status-failed)" },
  medium: { label: "中风险", color: "var(--color-status-warning)" },
  low: { label: "低风险", color: "var(--color-status-pending)" }
}

export const EXCEPTION_CATEGORIES: ExceptionCategoryMeta[] = [
  {
    key: "login_required",
    label: "需要重新登录",
    risk: "high",
    risk_label: "高风险",
    risk_color: "var(--color-status-failed)",
    judgment: "平台登录态失效，继续执行会重复失败。",
    suggested_steps: ["确认对应平台账号", "在浏览器完成登录", "登录后重新检测"]
  },
  {
    key: "config_missing",
    label: "需要配置补充",
    risk: "medium",
    risk_label: "中风险",
    risk_color: "var(--color-status-warning)",
    judgment: "当前任务缺少必要配置，不能继续自动执行。",
    suggested_steps: ["定位缺失配置项", "在规则与配置中心补充", "保存后重新检测"]
  },
  {
    key: "manual_review",
    label: "需要人工核对",
    risk: "medium",
    risk_label: "中风险",
    risk_color: "var(--color-status-warning)",
    judgment: "自动化结果需要人工确认后决定是否继续。",
    suggested_steps: ["查看错误原因与最近截图", "核对业务结果", "确认后继续执行或修正"]
  },
  {
    key: "auto_retry",
    label: "可以自动重试",
    risk: "low",
    risk_label: "低风险",
    risk_color: "var(--color-status-pending)",
    judgment: "属于临时性错误，可以安全重试。",
    suggested_steps: ["检查网络与平台状态", "确认重试次数未超限", "触发重新检测"]
  },
  {
    key: "page_changed",
    label: "页面可能改版",
    risk: "high",
    risk_label: "高风险",
    risk_color: "var(--color-status-failed)",
    judgment: "页面结构或选择器发生变化，自动化脚本需要更新。",
    suggested_steps: ["查看最近截图确认页面变化", "更新平台页面适配", "更新后重新检测"]
  },
  {
    key: "result_uncertain",
    label: "结果不确定",
    risk: "medium",
    risk_label: "中风险",
    risk_color: "var(--color-status-warning)",
    judgment: "写操作结果未确认，禁止直接重复执行。",
    suggested_steps: ["到外部平台对账确认结果", "有结果则补记完成", "确认未写入后再重试"]
  },
  {
    key: "account_structure",
    label: "账户表结构异常",
    risk: "high",
    risk_label: "高风险",
    risk_color: "var(--color-status-failed)",
    judgment: "飞书账户表结构不完整，无法安全分配账户。",
    suggested_steps: ["检查账户表块结构", "修正或追加标准账户块", "重新同步账户数据"]
  },
  {
    key: "feishu_partial_write",
    label: "飞书部分写入",
    risk: "high",
    risk_label: "高风险",
    risk_color: "var(--color-status-failed)",
    judgment: "飞书回填只完成一部分，存在脏数据风险。",
    suggested_steps: ["核对飞书实际写入内容", "人工修正部分写入", "确认一致后继续执行"]
  }
]

const CATEGORY_BY_KEY = new Map(
  EXCEPTION_CATEGORIES.map((category) => [category.key, category])
)

const CATEGORY_BY_LABEL = new Map(
  EXCEPTION_CATEGORIES.map((category) => [category.label, category])
)

const MESSAGE_KEYWORD_MAP: Array<[RegExp, ExceptionCategoryKey]> = [
  [/登录|登录态|重新登录|session|auth/i, "login_required"],
  [/缺少.*配置|配置缺失|配置不足|补充配置/i, "config_missing"],
  [/页面结构|页面可能改版|页面变化|选择器/i, "page_changed"],
  [/账户表结构|账户结构|结构异常|空位不足|无空位/i, "account_structure"],
  [/部分写入|回填失败|PARTIAL_WRITE|部分成功/i, "feishu_partial_write"],
  [/不确定|结果未知|结果不明确|RESULT_UNCERTAIN|超时/i, "result_uncertain"],
  [/重试|临时错误|网络|超时|RETRYABLE/i, "auto_retry"],
  [/人工复核|人工处理|人工核对|MANUAL_REVIEW/i, "manual_review"]
]

function matchByLabel(errorType?: string | null): ExceptionCategoryMeta | null {
  if (!errorType) return null
  const normalized = errorType.trim()
  const matched =
    CATEGORY_BY_KEY.get(normalized as ExceptionCategoryKey) ??
    CATEGORY_BY_LABEL.get(normalized)
  return matched ?? null
}

export function getExceptionCategoryMeta(
  key: ExceptionCategoryKey
): ExceptionCategoryMeta {
  return CATEGORY_BY_KEY.get(key) ?? EXCEPTION_CATEGORIES[2]
}

export function getRiskMeta(risk: RiskLevel | string): RiskMeta {
  return RISK_META[risk as RiskLevel] ?? RISK_META.medium
}

export function classifyException(
  message?: string | null,
  errorType?: string | null
): ExceptionCategoryMeta {
  const byType = matchByLabel(errorType)
  if (byType) return byType
  const text = message ?? ""
  for (const [pattern, key] of MESSAGE_KEYWORD_MAP) {
    if (pattern.test(text)) return getExceptionCategoryMeta(key)
  }
  return getExceptionCategoryMeta("manual_review")
}

export function formatDateTime(value?: string | null): string {
  const date = parseDateTimeUtc(value)
  if (!date) return value ?? "—"
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatDuration(
  start?: string | null,
  end?: string | null
): string {
  const startDate = parseDateTimeUtc(start)
  if (!startDate) return "—"
  const endDate = parseDateTimeUtc(end) ?? new Date()
  const diff = Math.max(0, endDate.getTime() - startDate.getTime())
  const minutes = Math.floor(diff / 60000)
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
  if (minutes > 0) return `${minutes}m`
  return `${Math.max(1, Math.floor(diff / 1000))}s`
}

export function formatRemainingTime(target?: string | null): string {
  const targetDate = parseDateTimeUtc(target)
  if (!targetDate) return "—"
  const diff = targetDate.getTime() - Date.now()
  if (diff <= 0) return "已到时间"
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时 ${minutes % 60} 分钟`
  return `${Math.floor(hours / 24)} 天`
}

export function formatFileSize(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export interface LedgerView {
  id: string
  taskId: string
  dramaName: string
  platform: string
  feishuRow: string
  sheetRow: string
  albumId: string
  productId: string
  externalTaskId: string
  taskName: string
  finalStatus: string
  finalStatusLabel: string
  ruleVersion: string
  configVersion: string
  completedAt: string
}

function text(value: unknown): string {
  return value ? String(value) : "—"
}

export function toLedgerView(ledger: Record<string, unknown>): LedgerView {
  return formatLedgerRow(ledger)
}

export function formatLedgerRow(ledger: Record<string, unknown>): LedgerView {
  return {
    id: text(ledger.id),
    taskId: text(ledger.task_id),
    dramaName: text(ledger.drama_name),
    platform: text(ledger.platform),
    feishuRow: text(ledger.feishu_row ?? ledger.sheet_row),
    sheetRow: text(ledger.sheet_row),
    albumId: text(ledger.album_id),
    productId: text(ledger.product_id),
    externalTaskId: text(ledger.external_task_id),
    taskName: text(ledger.task_name),
    finalStatus: text(ledger.final_status),
    finalStatusLabel: text(ledger.final_status),
    ruleVersion: text(ledger.rule_version),
    configVersion: text(ledger.config_version),
    completedAt: formatDateTime(ledger.completed_at as string | null | undefined)
  }
}
