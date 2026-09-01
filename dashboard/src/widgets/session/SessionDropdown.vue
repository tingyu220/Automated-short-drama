<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ElMessage, ElPopover } from "element-plus"
import { useSessionStore } from "@/app/stores/session"
import { useSystemStore } from "@/app/stores/system"
import StatusDot from "@/shared/ui/StatusDot.vue"

const sessionStore = useSessionStore()
const systemStore = useSystemStore()

const platformLabels: Record<string, string> = {
  worker: "Automation Worker",
  feishu: "飞书",
  tomato: "番茄",
  delivery: "投放系统",
  ocean: "巨量",
  youxuan: "优选",
}

const platformOrder = ["worker", "feishu", "tomato", "delivery", "ocean", "youxuan"]

const checkingPlatform = ref<string | null>(null)
const importingPlatform = ref<string | null>(null)
const checkNotices = ref<Record<string, string>>({})

const allStatuses = computed(() => {
  const workerOnline = systemStore.isWorkerOnline()
  const platforms = platformOrder.map((key) => {
    if (key === "worker") {
      return {
        key,
        label: platformLabels[key],
        value: workerOnline ? "在线" : "离线",
        online: workerOnline,
        running: false,
      }
    }
    const session = sessionStore.sessions[key]
    const online = session?.status === "logged_in"
    return {
      key,
      label: platformLabels[key],
      value: online ? "已登录" : "未登录",
      online,
      running: sessionStore.running[key] === true,
    }
  })
  return platforms
})

const sessionPlatforms = computed(() =>
  platformOrder.filter((p) => p !== "worker")
)

const summary = computed(() => {
  const total = sessionPlatforms.value.length
  const loggedIn = sessionPlatforms.value.filter(
    (key) => sessionStore.sessions[key]?.status === "logged_in"
  ).length
  return { total, loggedIn, allOk: loggedIn === total }
})

const summaryDotColor = computed(() => {
  if (summary.value.allOk) return "var(--color-status-success)"
  if (summary.value.loggedIn === 0) return "var(--color-status-error)"
  return "var(--color-status-warning)"
})

async function checkSession(platform: string) {
  checkingPlatform.value = platform
  const status = await sessionStore.check(platform)
  checkNotices.value = {
    ...checkNotices.value,
    [platform]: status
      ? status.status === "logged_in"
        ? "检测完成：已登录"
        : "检测完成：未登录，请重新登录"
      : sessionStore.error ?? "检测失败，请稍后重试",
  }
  checkingPlatform.value = null
}

async function importFromChrome(platform: string) {
  importingPlatform.value = platform
  const status = await sessionStore.importFromChrome(platform)
  checkNotices.value = {
    ...checkNotices.value,
    [platform]:
      status?.status === "logged_in"
        ? "Chrome 导入成功：已登录"
        : `Chrome 导入失败：${sessionStore.error ?? "未找到有效登录态"}`,
  }
  importingPlatform.value = null
}

async function handleLogin(platform: string) {
  try {
    await sessionStore.login(platform)
    ElMessage.success("已打开登录窗口，请在浏览器中完成登录")
  } catch {
    ElMessage.error(sessionStore.error ?? "启动登录失败")
  }
}

async function handleFinish(platform: string) {
  await sessionStore.finish(platform)
  ElMessage.success("已保存登录态")
}

async function handleReset(platform: string) {
  await sessionStore.reset(platform)
  ElMessage.info("登录状态已重置")
}

onMounted(() => {
  void sessionStore.fetchSessions()
})
</script>

<template>
  <el-popover
    placement="bottom-end"
    :width="400"
    trigger="click"
    popper-class="session-dropdown__popover"
  >
    <template #reference>
      <button class="session-dropdown__trigger">
        <StatusDot :color="summaryDotColor" />
        <span class="session-dropdown__label">平台登录</span>
        <span class="session-dropdown__count">{{ summary.loggedIn }}/{{ summary.total }}</span>
      </button>
    </template>

    <div class="session-dropdown__panel">
      <div class="session-dropdown__header">
        <span>Worker 与平台 Session</span>
      </div>
      <ul class="session-dropdown__list">
        <li
          v-for="item in allStatuses"
          :key="item.key"
          class="session-dropdown__item"
        >
          <div class="session-dropdown__item-main">
            <StatusDot
              :color="item.online ? 'var(--color-status-success)' : 'var(--color-status-pending)'"
              :active="item.online"
            />
            <span class="session-dropdown__item-label">{{ item.label }}</span>
            <span class="session-dropdown__item-value">{{ item.value }}</span>
          </div>
          <div class="session-dropdown__item-actions">
            <button
              v-if="item.key !== 'worker'"
              type="button"
              class="session-dropdown__action"
              :disabled="sessionStore.loading || checkingPlatform !== null"
              @click="checkSession(item.key)"
            >
              {{ checkingPlatform === item.key ? "检测中" : "检测" }}
            </button>
            <template
              v-if="item.key !== 'worker' && item.key !== 'feishu'"
            >
              <button
                v-if="item.running"
                type="button"
                class="session-dropdown__action"
                @click="handleFinish(item.key)"
              >
                完成登录
              </button>
              <button
                v-if="item.running"
                type="button"
                class="session-dropdown__action session-dropdown__action--reset"
                title="浏览器已关闭或卡住？点此重置"
                @click="handleReset(item.key)"
              >
                重置
              </button>
              <template v-else>
                <button
                  type="button"
                  class="session-dropdown__action"
                  @click="handleLogin(item.key)"
                >
                  {{ item.online ? "重新登录" : "去登录" }}
                </button>
                <button
                  type="button"
                  class="session-dropdown__action"
                  title="从本机 Chrome 读取登录 Cookie"
                  :disabled="sessionStore.loading"
                  @click="importFromChrome(item.key)"
                >
                  {{ importingPlatform === item.key ? "导入中" : "Chrome导入" }}
                </button>
              </template>
            </template>
          </div>
          <p
            v-if="checkNotices[item.key]"
            class="session-dropdown__notice"
          >
            {{ checkNotices[item.key] }}
          </p>
        </li>
      </ul>
    </div>
  </el-popover>
</template>

<style scoped>
.session-dropdown__trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.session-dropdown__trigger:hover {
  background: var(--color-bg-page);
}

.session-dropdown__label {
  color: var(--color-text-tertiary);
  font-weight: 500;
  white-space: nowrap;
}

.session-dropdown__count {
  color: var(--color-text-primary);
  font-weight: 600;
  white-space: nowrap;
}

.session-dropdown__panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-dropdown__header {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  padding-bottom: 4px;
  border-bottom: 1px solid #e5e7eb;
}

.session-dropdown__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  list-style: none;
  padding: 0;
  margin: 0;
}

.session-dropdown__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.session-dropdown__item-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.session-dropdown__item-label {
  flex: 1;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.session-dropdown__item-value {
  color: var(--color-text-primary);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.session-dropdown__item-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.session-dropdown__action {
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  padding: 2px 4px;
}

.session-dropdown__action:hover {
  text-decoration: underline;
}

.session-dropdown__action:disabled {
  cursor: wait;
  opacity: 0.55;
}

.session-dropdown__action--reset {
  color: var(--color-warning, #e6a23c);
}

.session-dropdown__notice {
  width: 100%;
  margin: 0;
  padding-left: 16px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}
</style>
