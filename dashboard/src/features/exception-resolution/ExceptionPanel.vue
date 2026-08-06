<script setup lang="ts">
import { computed, ref } from "vue"
import EmptyState from "@/shared/ui/EmptyState.vue"
import ErrorState from "@/shared/ui/ErrorState.vue"
import LoadingSkeleton from "@/shared/ui/LoadingSkeleton.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import { formatDateTime } from "@/shared/utils/format"
import type { ExceptionItem } from "@/app/stores/exception"

export type ExceptionAction =
  | "modify_config"
  | "relogin"
  | "view_screenshot"
  | "recheck"
  | "continue"

const props = defineProps<{
  items: ExceptionItem[]
  loading: boolean
  error: string | null
}>()

const emit = defineEmits<{
  (e: "retry"): void
  (e: "action", payload: { item: ExceptionItem; action: ExceptionAction }): void
}>()

const ACTION_LABEL: Record<ExceptionAction, string> = {
  modify_config: "修改配置",
  relogin: "重新登录",
  view_screenshot: "查看截图",
  recheck: "重新检测",
  continue: "继续执行"
}

const selectedId = ref<string | null>(props.items[0]?.id ?? null)
const selected = computed(
  () => props.items.find((item) => item.id === selectedId.value) ?? null
)

function select(item: ExceptionItem) {
  selectedId.value = item.id
}

function run(item: ExceptionItem, action: ExceptionAction) {
  emit("action", { item, action })
}

function relatedConfigText(item: ExceptionItem): string {
  if (!item.related_config) return "暂无相关配置"
  return Object.entries(item.related_config)
    .map(([key, value]) => `${key}：${String(value)}`)
    .join("；")
}

function suggestedSteps(item: ExceptionItem): string[] {
  return item.suggested_steps ?? []
}
</script>

<template>
  <section class="exception-panel">
    <ErrorState
      v-if="error"
      :message="error"
      retry-text="重新加载"
      @retry="emit('retry')"
    />
    <LoadingSkeleton
      v-else-if="loading && items.length === 0"
      :rows="5"
    />
    <EmptyState
      v-else-if="items.length === 0"
      title="暂无异常"
      description="当前没有需要处理的自动化异常"
    />
    <template v-else>
      <div class="exception-panel__layout">
        <div class="exception-panel__scroll">
          <table class="exception-panel__table">
            <thead>
              <tr>
                <th>剧名</th>
                <th>平台</th>
                <th>步骤</th>
                <th>错误类型</th>
                <th>业务描述</th>
                <th>发生时间</th>
                <th>重试次数</th>
                <th>风险等级</th>
                <th class="exception-panel__operations-head">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in items"
                :key="item.id"
                class="exception-panel__row"
                :class="{ 'is-selected': selectedId === item.id }"
                @click="select(item)"
              >
                <td class="exception-panel__drama">{{ item.drama_name || "未知剧名" }}</td>
                <td>{{ item.platform || "—" }}</td>
                <td>{{ item.step || "—" }}</td>
                <td>
                  <span class="exception-panel__type">{{ item.category_label }}</span>
                </td>
                <td class="exception-panel__message" :title="item.message">
                  {{ item.message }}
                </td>
                <td>{{ formatDateTime(item.occurred_at) }}</td>
                <td>{{ item.retry_count ?? 0 }}</td>
                <td>
                  <span class="exception-panel__risk">
                    <StatusDot :color="item.risk_color" />
                    {{ item.risk_label }}
                  </span>
                </td>
                <td class="exception-panel__operations" @click.stop>
                  <button
                    type="button"
                    class="exception-panel__action exception-panel__action--primary"
                    @click="run(item, 'modify_config')"
                  >
                    修改配置
                  </button>
                  <button
                    type="button"
                    class="exception-panel__action"
                    @click="run(item, 'recheck')"
                  >
                    重新检测
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <aside v-if="selected" class="exception-panel__detail">
          <header class="exception-panel__detail-head">
            <div>
              <h2 class="exception-panel__detail-title">{{ selected.drama_name || "未知剧名" }}</h2>
              <p class="exception-panel__detail-sub">{{ selected.category_label }} · {{ formatDateTime(selected.occurred_at) }}</p>
            </div>
            <span class="exception-panel__detail-risk">
              <StatusDot :color="selected.risk_color" />
              {{ selected.risk_label }}
            </span>
          </header>

          <dl class="exception-panel__detail-grid">
            <div class="exception-panel__field">
              <dt>错误原因</dt>
              <dd>{{ selected.message }}</dd>
            </div>
            <div class="exception-panel__field">
              <dt>系统判断</dt>
              <dd>{{ selected.category_label }}</dd>
            </div>
            <div class="exception-panel__field">
              <dt>最近截图</dt>
              <dd>
                <span v-if="selected.screenshot_urls?.length">
                  {{ selected.screenshot_urls[0] }}
                </span>
                <span v-else>暂无截图</span>
              </dd>
            </div>
            <div class="exception-panel__field">
              <dt>当前页面URL</dt>
              <dd class="exception-panel__mono">
                {{ selected.page_url || "—" }}
              </dd>
            </div>
            <div class="exception-panel__field exception-panel__field--full">
              <dt>相关配置</dt>
              <dd>{{ relatedConfigText(selected) }}</dd>
            </div>
            <div class="exception-panel__field exception-panel__field--full">
              <dt>建议处理步骤</dt>
              <dd>
                <ol v-if="suggestedSteps(selected).length" class="exception-panel__steps">
                  <li v-for="(step, index) in suggestedSteps(selected)" :key="index">
                    {{ step }}
                  </li>
                </ol>
                <span v-else>暂无建议</span>
              </dd>
            </div>
          </dl>

          <details class="exception-panel__stack">
            <summary>技术堆栈</summary>
            <pre>{{ selected.stack_trace || "暂无技术信息" }}</pre>
          </details>

          <footer class="exception-panel__actions">
            <button
              v-for="action in (['modify_config', 'relogin', 'view_screenshot', 'recheck', 'continue'] as ExceptionAction[])"
              :key="action"
              type="button"
              class="exception-panel__action"
              :class="{ 'exception-panel__action--primary': action === 'continue' }"
              @click="run(selected, action)"
            >
              {{ ACTION_LABEL[action] }}
            </button>
          </footer>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.exception-panel__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}

.exception-panel__scroll {
  min-width: 0;
  overflow-x: auto;
}

.exception-panel__table {
  width: 100%;
  min-width: 1080px;
  border-collapse: collapse;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
  font-size: var(--font-size-table);
}

.exception-panel__table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 10px 12px;
  background: var(--color-bg-panel-secondary);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #e5e7eb;
}

.exception-panel__table td {
  max-width: 220px;
  padding: 10px 12px;
  overflow: hidden;
  color: var(--color-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
  border-bottom: 1px solid #f0f1f3;
}

.exception-panel__table tbody tr {
  height: 48px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.exception-panel__table tbody tr:hover,
.exception-panel__table tbody tr.is-selected {
  background: var(--color-primary-50);
}

.exception-panel__table tbody tr:last-child td {
  border-bottom: none;
}

.exception-panel__drama {
  font-weight: 500;
}

.exception-panel__type {
  display: inline-flex;
  height: 22px;
  align-items: center;
  padding: 0 8px;
  color: var(--color-primary);
  background: var(--color-primary-50);
  border-radius: 999px;
  font-size: var(--font-size-caption);
  white-space: nowrap;
}

.exception-panel__risk {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.exception-panel__operations {
  position: sticky;
  right: 0;
  min-width: 170px;
  background: var(--color-bg-panel);
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.exception-panel__operations-head {
  right: 0;
  min-width: 170px;
  box-shadow: -4px 0 8px rgb(30 36 48 / 6%);
}

.exception-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid #f0f1f3;
}

.exception-panel__action {
  height: 28px;
  padding: 0 10px;
  border: 1px solid #d9dde3;
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.exception-panel__action:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-50);
}

.exception-panel__action--primary {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.exception-panel__detail {
  position: sticky;
  top: 0;
  min-width: 0;
  padding: 20px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.exception-panel__detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.exception-panel__detail-title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.exception-panel__detail-sub {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.exception-panel__detail-risk {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.exception-panel__detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.exception-panel__field {
  min-width: 0;
}

.exception-panel__field--full {
  grid-column: 1 / -1;
}

.exception-panel__field dt {
  margin-bottom: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.exception-panel__field dd {
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  line-height: 1.6;
  word-break: break-all;
}

.exception-panel__mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}

.exception-panel__steps {
  padding-left: 18px;
}

.exception-panel__steps li {
  margin-top: 4px;
}

.exception-panel__stack {
  margin-top: 16px;
  border-top: 1px solid #f0f1f3;
  padding-top: 12px;
}

.exception-panel__stack summary {
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  cursor: pointer;
}

.exception-panel__stack pre {
  margin-top: 8px;
  max-height: 180px;
  padding: 12px;
  overflow: auto;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-input);
  color: var(--color-text-secondary);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
  white-space: pre-wrap;
}

@media (max-width: 1440px) {
  .exception-panel__layout {
    grid-template-columns: minmax(0, 1fr) 320px;
  }
}

@media (max-width: 1200px) {
  .exception-panel__layout {
    grid-template-columns: 1fr;
  }

  .exception-panel__detail {
    position: static;
  }
}
</style>
