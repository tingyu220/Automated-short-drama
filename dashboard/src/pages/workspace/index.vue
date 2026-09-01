<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElButton, ElDrawer, ElMessage, ElTag } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import CurrentTaskPanel from "@/widgets/current-task/CurrentTaskPanel.vue"
import TaskDetailDrawer from "@/features/task-detail/TaskDetailDrawer.vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import { useMiniprogramStore } from "@/app/stores/miniprogram"
import { getPlatformLabel, getStatusColor, getStatusLabel } from "@/shared/utils/status"
import { useExceptionStore } from "@/app/stores/exception"
import { useQueueStore } from "@/app/stores/queue"
import { useSessionStore } from "@/app/stores/session"
import { useSystemStore } from "@/app/stores/system"
import { useTaskStore } from "@/app/stores/task"
import {
  formatDateTime,
  formatRemainingTime,
  isLeaseActive,
  parseTaskTime,
  toTaskView,
  type TaskView
} from "@/entities/task/types"

const taskStore = useTaskStore()
const queueStore = useQueueStore()
const exceptionStore = useExceptionStore()
const systemStore = useSystemStore()
const sessionStore = useSessionStore()
const miniprogramStore = useMiniprogramStore()
const route = useRoute()
const router = useRouter()

type ProductionLine = "A" | "B"
const activeTab = ref<ProductionLine>(
  (route.query.tab as ProductionLine) || "B"
)

watch(
  () => route.query.tab,
  (tab) => {
    if (tab === "A" || tab === "B") {
      activeTab.value = tab
    }
  }
)

watch(activeTab, (tab) => {
  if (tab === "A") {
    miniprogramStore.fetchTasks()
    miniprogramStore.fetchConfigs()
  }
})

async function handleSync() {
  const ok = await miniprogramStore.syncTasks()
  if (ok && miniprogramStore.syncResult) {
    const r = miniprogramStore.syncResult
    ElMessage.success(`同步完成: 新增 ${r.created} 更新 ${r.updated} 跳过 ${r.skipped}`)
  } else {
    ElMessage.error("同步失败，请检查后端和飞书连接")
  }
}

const checkingPlatform = ref<string | null>(null)
const importingPlatform = ref<string | null>(null)
const checkNotices = ref<Record<string, string>>({})
const detailOpen = ref(false)

type OverviewType = "all" | "extracted" | "ready" | "exception"
const overviewDrawerOpen = ref(false)
const overviewDrawerType = ref<OverviewType>("all")
const overviewDetailOpen = ref(false)
const overviewDetailTask = ref<TaskView | null>(null)

const TASK_PLATFORM_SESSION_KEYS: Record<string, string> = {
  TOMATO: "tomato",
  JUBIAN: "delivery",
  DELIVERY: "delivery",
  OCEAN: "ocean"
}

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

async function load() {
  await Promise.all([
    taskStore.fetchTasks({ date: today() }),
    queueStore.fetchQueue(),
    exceptionStore.fetchExceptions(),
    sessionStore.fetchSessions()
  ])
}

async function checkSession(platform: string) {
  checkingPlatform.value = platform
  const status = await sessionStore.check(platform)
  checkNotices.value = {
    ...checkNotices.value,
    [platform]: status
      ? status.status === "logged_in"
        ? "检测完成：已登录"
        : "检测完成：未登录，请重新登录"
      : sessionStore.error ?? "检测失败，请稍后重试"
  }
  checkingPlatform.value = null
}

async function importFromChrome(platform: string) {
  importingPlatform.value = platform
  const status = await sessionStore.importFromChrome(platform)
  checkNotices.value = {
    ...checkNotices.value,
    [platform]: status?.status === "logged_in"
      ? "Chrome 导入成功：已登录"
      : `Chrome 导入失败：${sessionStore.error ?? "未找到有效登录态"}`
  }
  importingPlatform.value = null
}

onMounted(load)

const current = computed(() => {
  const item = queueStore.items.find(
    (entry) =>
      (entry.state === "RUNNING" || entry.state === "CLAIMED") &&
      isLeaseActive(entry)
  )
  if (!item) return { task: null, item: null }
  return {
    task: taskStore.tasks.find((entry) => entry.id === item.task_id) ?? null,
    item
  }
})

const currentDetail = computed<TaskView | null>(() => {
  const detail = taskStore.detail
  if (detail && detail.id === current.value.task?.id) {
    return toTaskView(detail)
  }
  return current.value.task ? toTaskView(current.value.task) : null
})

function openCurrentPlatform() {
  const task = current.value.task
  if (!task) return
  const sessionKey = TASK_PLATFORM_SESSION_KEYS[task.platform.toUpperCase()]
  const url = sessionKey ? sessionStore.sessions[sessionKey]?.login_url : null
  if (!url) {
    ElMessage.warning("未找到该任务的平台地址，请先刷新平台 Session")
    return
  }
  window.open(url, "_blank", "noopener,noreferrer")
}

async function viewCurrentTask() {
  const task = current.value.task
  if (!task) return
  detailOpen.value = true
  await taskStore.fetchTask(task.id)
  if (taskStore.error) ElMessage.error(taskStore.error)
}

function openOverview(type: OverviewType) {
  overviewDrawerType.value = type
  overviewDrawerOpen.value = true
}

const overviewDrawerTitle = computed(() => {
  const labels: Record<OverviewType, string> = {
    all: "今日剧目",
    extracted: "已提取链接",
    ready: "链接已就绪",
    exception: "异常任务"
  }
  const label = labels[overviewDrawerType.value]
  const count = overviewDrawerItems.value.length
  return `${label} · ${count} 个`
})

const overviewDrawerItems = computed(() => {
  const readyStatuses = new Set(["LINK_READY", "COMPLETED"])
  const extractedStatuses = new Set(["LINK_EXTRACTED", "LINK_READY", "COMPLETED"])
  switch (overviewDrawerType.value) {
    case "extracted":
      return taskStore.tasks.filter((t) => extractedStatuses.has(t.status))
    case "ready":
      return taskStore.tasks.filter((t) => readyStatuses.has(t.status))
    case "exception":
      return exceptionStore.exceptions.map((ex) => ({
        id: ex.task_id,
        drama_name: ex.drama_name ?? taskStore.tasks.find((t) => t.id === ex.task_id)?.drama_name ?? "—",
        platform: ex.platform ?? taskStore.tasks.find((t) => t.id === ex.task_id)?.platform ?? "",
        status: ex.failure_code ?? ex.level ?? "MANUAL_REVIEW",
        available_time: ex.occurred_at,
        updated_at: ex.occurred_at,
        failure_message: ex.message,
        queue_state: null,
        owner: null,
        current_stage: null,
        target_stage: null
      }))
    default:
      return taskStore.tasks
  }
})

async function openOverviewDetail(taskId: string) {
  await taskStore.fetchTask(taskId)
  if (taskStore.detail) {
    overviewDetailTask.value = toTaskView(taskStore.detail)
    overviewDetailOpen.value = true
  } else if (taskStore.error) {
    ElMessage.error(taskStore.error)
  }
}

async function runTaskToTarget(targetStage: string) {
  const task = currentDetail.value ?? overviewDetailTask.value
  if (!task) return
  await taskStore.enqueueTask(task.id, targetStage)
  if (taskStore.error) {
    ElMessage.error(taskStore.error)
    return
  }
  ElMessage.success(
    targetStage === "LINK_EXTRACTION" ? "已安排提取链接" : "已安排搭建链接"
  )
  await load()
  if (taskStore.detail?.id === task.id) {
    await taskStore.fetchTask(task.id)
  }
}

const upcomingTasks = computed(() =>
  [...taskStore.tasks]
    .filter(
      (task) =>
        (parseTaskTime(task.available_time)?.getTime() ?? 0) >= Date.now()
    )
    .sort(
      (a, b) =>
        (parseTaskTime(a.available_time)?.getTime() ?? 0) -
        (parseTaskTime(b.available_time)?.getTime() ?? 0)
    )
    .slice(0, 6)
)

const exceptionRows = computed(() =>
  exceptionStore.exceptions.slice(0, 5).map((item) => ({
    ...item,
    dramaName:
      taskStore.tasks.find((task) => task.id === item.task_id)?.drama_name ?? "—"
  }))
)

const pendingQueue = computed(() =>
  queueStore.items
    .filter((item) =>
      [
        "WAITING_TIME",
        "QUEUED",
        "CLAIMED",
        "RUNNING",
        "RETRY_WAIT",
        "MANUAL_REVIEW"
      ].includes(item.state)
    )
    .sort((a, b) => {
      const aTime = parseTaskTime(a.available_at)?.getTime() ?? 0
      const bTime = parseTaskTime(b.available_at)?.getTime() ?? 0
      return aTime - bTime || a.priority - b.priority
    })
    .slice(0, 8)
)

const queueStateLabels: Record<string, string> = {
  WAITING_TIME: "等待上线",
  QUEUED: "待执行",
  CLAIMED: "已认领",
  RUNNING: "运行中",
  RETRY_WAIT: "待重试",
  MANUAL_REVIEW: "需人工处理"
}

const todayOverview = computed(() => {
  const readyStatuses = new Set(["LINK_READY", "COMPLETED"])
  const extractedStatuses = new Set([
    "LINK_EXTRACTED",
    "LINK_READY",
    "COMPLETED"
  ])
  return [
    { label: "今日剧目", value: taskStore.tasks.length, tone: "neutral" },
    {
      label: "已提取链接",
      value: taskStore.tasks.filter((task) => extractedStatuses.has(task.status)).length,
      tone: "info"
    },
    {
      label: "链接已就绪",
      value: taskStore.tasks.filter((task) => readyStatuses.has(task.status)).length,
      tone: "success"
    },
    {
      label: "异常任务",
      value: exceptionStore.exceptions.length,
      tone: exceptionStore.exceptions.length > 0 ? "warning" : "neutral"
    }
  ]
})

const activityRows = computed(() => {
  const exceptionActivities = exceptionRows.value.map((item) => ({
    id: `exception-${item.id}`,
    title: item.message,
    detail: `${item.dramaName} · ${formatDateTime(item.occurred_at)}`,
    timestamp: item.occurred_at,
    tone: "warning"
  }))
  const taskActivities = taskStore.tasks.map((task) => ({
    id: `task-${task.id}`,
    title: `${task.drama_name} 状态更新为 ${task.status}`,
    detail: `${getPlatformLabel(task.platform)} · ${formatDateTime(task.updated_at)}`,
    timestamp: task.updated_at,
    tone: "info"
  }))
  return [...exceptionActivities, ...taskActivities]
    .sort(
      (a, b) =>
        (parseTaskTime(b.timestamp)?.getTime() ?? 0) -
        (parseTaskTime(a.timestamp)?.getTime() ?? 0)
    )
    .slice(0, 6)
})

const resourceStatuses = computed(() => {
  const workerOnline = systemStore.isWorkerOnline()
  const platformStatus = (key: string, label: string) => {
    const session = sessionStore.sessions[key]
    const online = session?.status === "logged_in"
    return {
      key,
      label,
      value: online ? "已登录" : "未登录",
      online,
      running: sessionStore.running[key] === true
    }
  }
  return [
    {
      key: "worker",
      label: "Automation Worker",
      value: workerOnline ? "在线" : "离线",
      online: workerOnline,
      running: false
    },
    platformStatus("feishu", "飞书"),
    platformStatus("tomato", "番茄"),
    platformStatus("delivery", "投放系统"),
    platformStatus("ocean", "巨量"),
    platformStatus("youxuan", "优选")
  ]
})

function miniprogramStatusMeta(status: string): { label: string; color: string } {
  const map: Record<string, { label: string; color: string }> = {
    NOT_STARTED: { label: "未开始", color: "var(--color-status-pending)" },
    CONTEXT_READY: { label: "上下文就绪", color: "var(--color-status-running)" },
    DISCOVERY_READY: { label: "发现就绪", color: "var(--color-status-running)" },
    READY_FOR_IMPLEMENTATION: { label: "待实施", color: "var(--color-status-success)" },
    MANUAL_REVIEW: { label: "人工审核", color: "var(--color-status-error)" },
    FAILED: { label: "失败", color: "var(--color-status-error)" },
  }
  return map[status] ?? { label: status, color: "var(--color-status-pending)" }
}
</script>

<template>
  <div class="workspace">
    <header class="workspace__header">
      <div>
        <h1 class="workspace__title">工作台</h1>
        <p class="workspace__subtitle">今日自动化投放任务运行总览</p>
      </div>
      <ElButton :loading="taskStore.loading" @click="load">
        <el-icon><Refresh /></el-icon>
        刷新
      </ElButton>
    </header>

    <!-- 产线 Tab 切换 -->
    <div class="workspace__tabs">
      <button
        v-for="tab in [
          { key: 'A', label: 'A产线·小程序' },
          { key: 'B', label: 'B产线·端原生' }
        ]"
        :key="tab.key"
        class="workspace__tab"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key as ProductionLine"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- A产线·小程序 -->
    <div v-if="activeTab === 'A'" class="workspace__miniprogram">
      <!-- 小程序剧目表 -->
      <section class="miniprogram-section">
        <div class="miniprogram-section__header">
          <h3 class="miniprogram-section__title">小程序剧目</h3>
          <div class="miniprogram-section__actions">
            <ElButton size="small" :loading="miniprogramStore.syncing" @click="handleSync">从飞书同步</ElButton>
            <ElButton size="small" :loading="miniprogramStore.tasksLoading" @click="miniprogramStore.fetchTasks()">刷新</ElButton>
          </div>
        </div>
        <ErrorState
          v-if="miniprogramStore.tasksError"
          :message="miniprogramStore.tasksError"
          retry-text="重试"
          @retry="miniprogramStore.fetchTasks()"
        />
        <LoadingSkeleton v-else-if="miniprogramStore.tasksLoading && miniprogramStore.tasks.length === 0" :rows="4" />
        <EmptyState
          v-else-if="miniprogramStore.tasks.length === 0"
          title="暂无小程序剧目"
          description="后端启动后从飞书剧目表同步"
        />
        <div v-else class="mp-drama-list">
          <div
            v-for="task in miniprogramStore.tasks"
            :key="task.task_id"
            class="mp-drama-card"
          >
            <div class="mp-drama-card__header">
              <div class="mp-drama-card__title">
                <span class="mp-drama-card__name">{{ task.drama_name }}</span>
                <ElTag size="small" type="info">{{ task.operator_name }}</ElTag>
                <ElTag size="small" type="info">{{ task.organization_group }}</ElTag>
              </div>
              <ElTag
                size="small"
                :type="task.workflow_status === 'READY_FOR_IMPLEMENTATION' ? 'success' : task.workflow_status === 'FAILED' ? 'danger' : 'warning'"
              >
                {{ miniprogramStatusMeta(task.workflow_status).label }}
              </ElTag>
            </div>

            <!-- 工作流步骤 -->
            <div class="mp-steps">
              <div class="mp-step" :class="{ done: task.album_id }">
                <span class="mp-step__icon">{{ task.album_id ? '✓' : '○' }}</span>
                <span class="mp-step__label">专辑ID</span>
                <span class="mp-step__value">{{ task.album_id || '待获取' }}</span>
              </div>
              <div class="mp-step__arrow">→</div>
              <div class="mp-step" :class="{ done: task.drama_short_name }">
                <span class="mp-step__icon">{{ task.drama_short_name ? '✓' : '○' }}</span>
                <span class="mp-step__label">剧名缩写</span>
                <span class="mp-step__value">{{ task.drama_short_name || '待确认' }}</span>
              </div>
              <div class="mp-step__arrow">→</div>
              <div class="mp-step">
                <span class="mp-step__icon">○</span>
                <span class="mp-step__label">推广链接</span>
                <span class="mp-step__value">2.9 / 9.9</span>
              </div>
              <div class="mp-step__arrow">→</div>
              <div class="mp-step">
                <span class="mp-step__icon">○</span>
                <span class="mp-step__label">商品创建</span>
                <span class="mp-step__value">2.9 / 9.9</span>
              </div>
              <div class="mp-step__arrow">→</div>
              <div class="mp-step">
                <span class="mp-step__icon">○</span>
                <span class="mp-step__label">小程序资产</span>
                <span class="mp-step__value">2.9 / 9.9</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 固定配置 -->
      <section class="miniprogram-section">
        <h3 class="miniprogram-section__title">剧场配置</h3>
        <ErrorState
          v-if="miniprogramStore.configsError"
          :message="miniprogramStore.configsError"
          retry-text="重试"
          @retry="miniprogramStore.fetchConfigs()"
        />
        <LoadingSkeleton v-else-if="miniprogramStore.configsLoading && miniprogramStore.configs.length === 0" :rows="2" />
        <EmptyState
          v-else-if="miniprogramStore.configs.length === 0"
          title="暂无配置"
          description="在 backend/miniprogram/configs/ 下添加 YAML"
        />
        <div v-else class="miniprogram-configs">
          <div
            v-for="cfg in miniprogramStore.configs"
            :key="cfg.config_name"
            class="miniprogram-config-card"
          >
            <div class="miniprogram-config-card__header">
              <span class="miniprogram-config-card__name">{{ cfg.mini_program.name }}</span>
              <ElTag size="small">{{ cfg.config_name }}</ElTag>
            </div>
            <div class="miniprogram-config-card__body">
              <div class="miniprogram-config-row">
                <span class="miniprogram-config-label">AppID</span>
                <code>{{ cfg.mini_program.app_id }}</code>
              </div>
              <div class="miniprogram-config-row">
                <span class="miniprogram-config-label">原始ID</span>
                <code>{{ cfg.mini_program.original_id }}</code>
              </div>
              <div class="miniprogram-config-row">
                <span class="miniprogram-config-label">主体</span>
                <span>{{ cfg.ocean?.subject || '—' }}</span>
              </div>
              <div class="miniprogram-config-row">
                <span class="miniprogram-config-label">收费类型</span>
                <span>{{ cfg.promotion.charge_type }}</span>
              </div>
              <div class="miniprogram-config-row">
                <span class="miniprogram-config-label">价格档位</span>
                <div class="miniprogram-config-tiers">
                  <ElTag
                    v-for="(tierCfg, tier) in cfg.price_tiers"
                    :key="tier"
                    size="small"
                    type="success"
                  >
                    {{ tier }} — {{ tierCfg.product_library }}
                  </ElTag>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- A/B 产线内容 -->
    <template v-else>
    <div class="workspace__current">
        <CurrentTaskPanel
          :task="current.task"
          :queue-item="current.item"
          :loading="queueStore.loading"
          :current-step="current.task?.current_stage ?? null"
          @open-platform="openCurrentPlatform"
          @view="viewCurrentTask"
        />
    </div>

    <div class="workspace__operations">
      <section class="workspace-panel workspace-panel--queue">
        <header class="workspace-panel__header">
          <div>
            <h2 class="workspace-panel__title">待处理队列</h2>
            <p class="workspace-panel__hint">按执行时间和优先级排列</p>
          </div>
          <button
            type="button"
            class="workspace-panel__more"
            @click="router.push('/queue')"
          >
            查看全部
          </button>
        </header>
        <EmptyState
          v-if="pendingQueue.length === 0"
          title="暂无待处理任务"
          description="新的剧目到达上线时间后会自动进入队列"
        />
        <ul v-else class="workspace-panel__list workspace-panel__list--scroll">
          <li v-for="item in pendingQueue" :key="item.id" class="queue-item">
            <button type="button" class="queue-item__button" @click="router.push('/queue')">
              <span class="queue-item__main">
                <strong>{{ item.drama_name || taskStore.tasks.find((task) => task.id === item.task_id)?.drama_name || `任务 ${item.task_id}` }}</strong>
                <span>{{ getPlatformLabel(taskStore.tasks.find((task) => task.id === item.task_id)?.platform || '') }}</span>
              </span>
              <span class="queue-item__meta">
                <span class="queue-item__state">{{ queueStateLabels[item.state] || item.state }}</span>
                <span>{{ formatDateTime(item.available_at) }}</span>
              </span>
            </button>
          </li>
        </ul>
      </section>

      <section class="workspace-panel workspace-panel--overview">
        <header class="workspace-panel__header">
          <div>
            <h2 class="workspace-panel__title">今日运行概览</h2>
            <p class="workspace-panel__hint">北京时间 · 最近更新 {{ formatDateTime(taskStore.tasks[0]?.updated_at) }}</p>
          </div>
          <button
            type="button"
            class="workspace-panel__more"
            @click="router.push('/tasks')"
          >
            任务列表
          </button>
        </header>
        <dl class="overview-metrics">
          <div
            v-for="(metric, idx) in todayOverview"
            :key="metric.label"
            class="overview-metric overview-metric--clickable"
            @click="openOverview(['all', 'extracted', 'ready', 'exception'][idx] as OverviewType)"
          >
            <dt>{{ metric.label }}</dt>
            <dd :class="`overview-metric--${metric.tone}`">{{ taskStore.loading ? "—" : metric.value }}</dd>
          </div>
        </dl>
        <div class="overview-progress" aria-label="链接就绪进度">
          <div class="overview-progress__label">
            <span>链接就绪进度</span>
            <strong>{{ todayOverview[2].value }} / {{ todayOverview[0].value }}</strong>
          </div>
          <div class="overview-progress__track">
            <span :style="{ width: `${todayOverview[0].value ? Math.round((todayOverview[2].value / todayOverview[0].value) * 100) : 0}%` }" />
          </div>
        </div>
      </section>
    </div>

    <div class="workspace__activity">
      <section class="workspace-panel workspace-panel--activity">
        <header class="workspace-panel__header">
          <div>
            <h2 class="workspace-panel__title">最近活动</h2>
            <p class="workspace-panel__hint">自动化执行和异常变化</p>
          </div>
          <button type="button" class="workspace-panel__more" @click="router.push('/exceptions')">
            异常中心
          </button>
        </header>
        <EmptyState
          v-if="activityRows.length === 0"
          title="暂无最近活动"
          description="任务开始运行后，执行记录会显示在这里"
        />
        <ul v-else class="workspace-panel__list workspace-panel__list--scroll activity-list">
          <li v-for="item in activityRows" :key="item.id" class="activity-item">
            <span class="activity-item__dot" :class="`activity-item__dot--${item.tone}`" />
            <div>
              <strong>{{ item.title }}</strong>
              <span>{{ item.detail }}</span>
            </div>
          </li>
        </ul>
      </section>

      <aside class="workspace__secondary">
        <section class="workspace-panel">
          <header class="workspace-panel__header">
            <h2 class="workspace-panel__title">即将到时间</h2>
            <button
              type="button"
              class="workspace-panel__more"
              @click="router.push('/tasks')"
            >
              查看全部
            </button>
          </header>
          <EmptyState
            v-if="upcomingTasks.length === 0"
            title="暂无即将到时间任务"
            description="今天的任务时间均已完成或尚未同步"
          />
          <ul v-else class="workspace-panel__list">
            <li v-for="task in upcomingTasks" :key="task.id" class="upcoming-item">
              <div class="upcoming-item__main">
                <span class="upcoming-item__drama">{{ task.drama_name }}</span>
                <span class="upcoming-item__platform">
                  {{ getPlatformLabel(task.platform) }}
                </span>
              </div>
              <div class="upcoming-item__meta">
                <span>{{ formatDateTime(task.available_time) }}</span>
                <span class="upcoming-item__remaining">
                  {{ formatRemainingTime(task.available_time) }}
                </span>
              </div>
            </li>
          </ul>
        </section>

        <section class="workspace-panel">
          <header class="workspace-panel__header">
            <h2 class="workspace-panel__title">Worker 与平台 Session</h2>
          </header>
          <ul class="resource-list">
            <li v-for="item in resourceStatuses" :key="item.label" class="resource-item">
              <StatusDot
                :color="item.online ? 'var(--color-status-success)' : 'var(--color-status-pending)'"
                :active="item.online"
              />
              <span class="resource-item__label">{{ item.label }}</span>
              <span class="resource-item__value">{{ item.value }}</span>
              <button
                v-if="item.key !== 'worker'"
                type="button"
                class="resource-item__check"
                :disabled="sessionStore.loading || checkingPlatform !== null"
                @click="checkSession(item.key)"
              >
                {{ checkingPlatform === item.key ? "检测中" : "检测" }}
              </button>
              <span
                v-if="checkNotices[item.key]"
                class="resource-item__notice"
                role="status"
              >{{ checkNotices[item.key] }}</span>
              <template
                v-if="
                  item.key !== 'worker' &&
                  item.key !== 'feishu'
                "
              >
                <button
                  v-if="item.running"
                  class="resource-item__login"
                  @click="sessionStore.finish(item.key)"
                >
                  完成登录
                </button>
                <button
                  v-if="item.running"
                  class="resource-item__login resource-item__login--reset"
                  title="浏览器已关闭或卡住？点此重置"
                  @click="sessionStore.reset(item.key)"
                >
                  重置
                </button>
                <template v-else>
                  <button
                    class="resource-item__login"
                    @click="sessionStore.login(item.key)"
                  >
                    {{ item.online ? '重新登录' : '去登录' }}
                  </button>
                  <button
                    class="resource-item__login"
                    title="从本机 Chrome 读取登录 Cookie"
                    :disabled="sessionStore.loading"
                    @click="importFromChrome(item.key)"
                  >
                    {{ importingPlatform === item.key ? "导入中" : "Chrome导入" }}
                  </button>
                </template>
              </template>
            </li>
          </ul>
        </section>
      </aside>
    </div>

    </template>

    <TaskDetailDrawer
      :open="detailOpen"
      :task="currentDetail"
      @run="runTaskToTarget"
      @update:open="detailOpen = $event"
    />

    <ElDrawer
      v-model="overviewDrawerOpen"
      :title="overviewDrawerTitle"
      direction="rtl"
      size="420px"
    >
      <EmptyState
        v-if="overviewDrawerItems.length === 0"
        title="暂无数据"
        description="当前筛选条件下没有任务"
      />
      <ul v-else class="overview-drawer-list">
        <li
          v-for="item in overviewDrawerItems"
          :key="item.id"
          class="overview-drawer-item"
          @click="openOverviewDetail(item.id)"
        >
          <div class="overview-drawer-item__header">
            <strong>{{ item.drama_name }}</strong>
            <ElTag size="small" :color="getStatusColor(item.status)" effect="plain">
              {{ getStatusLabel(item.status) }}
            </ElTag>
          </div>
          <div class="overview-drawer-item__meta">
            <span>{{ getPlatformLabel(item.platform) }}</span>
            <span>{{ formatDateTime(item.available_time) }}</span>
          </div>
          <div
            v-if="(item as any).failure_message"
            class="overview-drawer-item__error"
          >
            {{ (item as any).failure_message }}
          </div>
        </li>
      </ul>
    </ElDrawer>

    <TaskDetailDrawer
      :open="overviewDetailOpen"
      :task="overviewDetailTask"
      @run="runTaskToTarget"
      @update:open="overviewDetailOpen = $event"
    />
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.workspace__tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--color-border-light, #e5e7eb);
  padding-bottom: 0;
}

.workspace__tab {
  padding: 8px 20px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s ease;
}

.workspace__tab:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-muted, #f8fafc);
  border-radius: 6px 6px 0 0;
}

.workspace__tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}

.workspace__miniprogram {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.miniprogram-section {
  margin-bottom: 8px;
}

.miniprogram-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.miniprogram-section__actions {
  display: flex;
  gap: 8px;
}

.miniprogram-section__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.miniprogram-status-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-left: 6px;
}

.miniprogram-configs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.miniprogram-config-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-card, 12px);
  border: 1px solid var(--color-border-light, #e5e7eb);
  padding: 20px;
}

.miniprogram-config-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.miniprogram-config-card__name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.miniprogram-config-card__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.miniprogram-config-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.miniprogram-config-label {
  color: var(--color-text-tertiary);
  min-width: 80px;
}

.miniprogram-config-row code {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  color: var(--color-text-primary);
  background: var(--color-bg-muted, #f8fafc);
  padding: 2px 6px;
  border-radius: 4px;
}

.mp-drama-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mp-drama-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light, #e5e7eb);
  border-radius: 12px;
  padding: 16px 20px;
}

.mp-drama-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.mp-drama-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mp-drama-card__name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.mp-steps {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.mp-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--color-bg-muted, #f8fafc);
  font-size: 13px;
}

.mp-step.done {
  background: rgba(34, 197, 94, 0.08);
}

.mp-step__icon {
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  background: #e5e7eb;
  color: #9ca3af;
}

.mp-step.done .mp-step__icon {
  background: #22c55e;
  color: white;
}

.mp-step__label {
  color: var(--color-text-secondary);
  font-weight: 500;
  white-space: nowrap;
}

.mp-step__value {
  color: var(--color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}

.mp-step.done .mp-step__value {
  color: #16a34a;
}

.mp-step__arrow {
  color: #d1d5db;
  font-size: 14px;
  margin: 0 2px;
}

.workspace__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.workspace__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.workspace__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}

.workspace__current {
  min-width: 0;
}

.workspace__operations {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(360px, 1fr);
  gap: 20px;
  align-items: stretch;
}

.workspace__activity {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 1fr);
  gap: 20px;
  align-items: start;
}

.workspace__secondary {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workspace-panel--queue,
.workspace-panel--overview,
.workspace-panel--activity {
  min-width: 0;
}

.workspace-panel__hint {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.workspace-panel__list--scroll {
  max-height: 300px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.queue-item {
  border-bottom: 1px solid #f0f1f3;
}

.queue-item:last-child {
  border-bottom: none;
}

.queue-item__button {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 11px 4px;
  border: none;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.queue-item__button:hover {
  background: var(--color-bg-panel-secondary);
}

.queue-item__main,
.queue-item__meta {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.queue-item__main {
  flex: 1;
}

.queue-item__main strong,
.activity-item strong {
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-item__main span,
.queue-item__meta,
.activity-item span {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.queue-item__meta {
  align-items: flex-end;
  flex: none;
  white-space: nowrap;
}

.queue-item__state {
  color: var(--color-primary);
  font-weight: 500;
}

.overview-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.overview-metric {
  padding: 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-button);
}

.overview-metric--clickable {
  cursor: pointer;
  transition: background 0.15s ease, box-shadow 0.15s ease;
}

.overview-metric--clickable:hover {
  background: var(--color-bg-panel-hover, #eef0f4);
  box-shadow: 0 0 0 1px var(--color-primary) inset;
}

.overview-metric dt {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.overview-metric dd {
  margin-top: 6px;
  color: var(--color-text-primary);
  font-size: 24px;
  font-weight: 600;
}

.overview-metric--info {
  color: var(--color-primary) !important;
}

.overview-metric--success {
  color: var(--color-status-success) !important;
}

.overview-metric--warning {
  color: var(--color-status-warning) !important;
}

.overview-progress {
  margin-top: 18px;
}

.overview-progress__label {
  display: flex;
  justify-content: space-between;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.overview-progress__label strong {
  color: var(--color-text-primary);
  font-weight: 500;
}

.overview-progress__track {
  height: 6px;
  margin-top: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--color-bg-panel-secondary);
}

.overview-progress__track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-primary);
  transition: width 0.25s ease;
}

.overview-drawer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin: 0;
}

.overview-drawer-item {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-button);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.overview-drawer-item:hover {
  border-color: var(--color-primary);
  background: var(--color-bg-panel-secondary);
}

.overview-drawer-item__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.overview-drawer-item__header strong {
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-drawer-item__meta {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.overview-drawer-item__error {
  margin-top: 6px;
  padding: 6px 8px;
  background: #fef0f0;
  border-radius: 4px;
  color: #f56c6c;
  font-size: var(--font-size-caption);
  line-height: 1.4;
}

.activity-list {
  max-height: 260px;
}

.activity-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 4px;
  border-bottom: 1px solid #f0f1f3;
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-item > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.activity-item__dot {
  width: 8px;
  height: 8px;
  margin-top: 5px;
  flex: none;
  border-radius: 50%;
  background: var(--color-status-pending);
}

.activity-item__dot--warning {
  background: var(--color-status-warning);
}

.activity-item__dot--info {
  background: var(--color-primary);
}

.workspace-panel {
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.workspace-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.workspace-panel__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.workspace-panel__more {
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}

.workspace-panel__more:hover {
  text-decoration: underline;
}

.workspace-panel__list {
  display: flex;
  flex-direction: column;
  list-style: none;
}

.upcoming-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f1f3;
}

.upcoming-item:last-child {
  border-bottom: none;
}

.upcoming-item__main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.upcoming-item__drama {
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upcoming-item__platform {
  flex: none;
  padding: 2px 8px;
  color: var(--color-text-secondary);
  background: var(--color-bg-panel-secondary);
  border-radius: 999px;
  font-size: var(--font-size-caption);
}

.upcoming-item__meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
  white-space: nowrap;
}

.upcoming-item__remaining {
  color: var(--color-primary);
  font-weight: 500;
}

.resource-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  list-style: none;
}

.resource-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.resource-item__label {
  flex: 1;
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
}

.resource-item__value {
  color: var(--color-text-primary);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.resource-item__notice {
  width: 100%;
  margin-left: 16px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.resource-item__check,
.resource-item__login {
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-size: var(--font-size-caption);
  cursor: pointer;
  white-space: nowrap;
}

.resource-item__check:disabled,
.resource-item__login:disabled {
  cursor: wait;
  opacity: 0.55;
}

.resource-item__login {
  text-decoration: none;
}

.resource-item__login:hover {
  text-decoration: underline;
}

.resource-item__login--reset {
  color: var(--color-warning, #e6a23c);
}

@media (max-width: 1280px) {
  .workspace__operations,
  .workspace__activity {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .workspace {
    gap: 14px;
  }

  .workspace__header {
    align-items: flex-start;
  }

  .workspace-panel {
    padding: 14px;
  }

  .overview-metrics {
    gap: 10px;
  }

  .overview-metric dd {
    font-size: 20px;
  }
}
</style>
