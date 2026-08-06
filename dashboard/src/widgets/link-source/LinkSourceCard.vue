<script setup lang="ts">
import { computed, ref } from "vue"
import { ElMessage } from "element-plus"
import StatusDot from "@/shared/ui/StatusDot.vue"
import {
  getLinkStatusMeta,
  maskUrl,
  type PromotionLink
} from "@/entities/task/types"

const props = defineProps<{ link: PromotionLink }>()
const emit = defineEmits<{
  (e: "copy", link: PromotionLink): void
  (e: "expand", link: PromotionLink): void
}>()

const expanded = ref(false)
const meta = computed(() => getLinkStatusMeta(props.link.status))
const displayUrl = computed(() =>
  expanded.value ? props.link.url : maskUrl(props.link.url)
)
const hasUrl = computed(() => Boolean(props.link.url))

async function copyLink() {
  if (!hasUrl.value) return
  try {
    await navigator.clipboard.writeText(props.link.url)
    ElMessage.success("链接已复制")
    emit("copy", props.link)
  } catch {
    ElMessage.warning("复制失败，请手动选择链接")
  }
}

function toggleExpand() {
  if (!hasUrl.value) return
  expanded.value = !expanded.value
  emit("expand", props.link)
}
</script>

<template>
  <article class="link-source-card">
    <header class="link-source-card__header">
      <span class="link-source-card__label">{{ link.label }}</span>
      <span class="link-source-card__status">
        <StatusDot :color="meta.color" />
        {{ meta.label }}
      </span>
    </header>

    <dl class="link-source-card__grid">
      <div>
        <dt>来源</dt>
        <dd>{{ link.source || "—" }}</dd>
      </div>
      <div>
        <dt>入口</dt>
        <dd>{{ link.entry || "—" }}</dd>
      </div>
      <div>
        <dt>获取方式</dt>
        <dd>{{ link.method || "—" }}</dd>
      </div>
      <div v-if="link.selection">
        <dt>选集</dt>
        <dd>{{ link.selection }}</dd>
      </div>
      <div v-if="link.template">
        <dt>模板</dt>
        <dd>{{ link.template }}</dd>
      </div>
      <div v-if="link.price">
        <dt>档位价格</dt>
        <dd>{{ link.price }}</dd>
      </div>
      <div v-if="link.target_price">
        <dt>目标价格</dt>
        <dd>{{ link.target_price }}</dd>
      </div>
      <div v-if="link.price_diff">
        <dt>价格差</dt>
        <dd>{{ link.price_diff }}</dd>
      </div>
      <div v-if="link.extracted_at">
        <dt>提取时间</dt>
        <dd>{{ link.extracted_at }}</dd>
      </div>
      <div v-if="link.rule_version">
        <dt>规则版本</dt>
        <dd>{{ link.rule_version }}</dd>
      </div>
    </dl>

    <div class="link-source-card__url">
      <span v-if="hasUrl" class="link-source-card__url-text">{{ displayUrl }}</span>
      <span v-else class="link-source-card__url-empty">尚未提取推广链接</span>
      <div class="link-source-card__actions">
        <button type="button" :disabled="!hasUrl" @click="copyLink">复制</button>
        <button type="button" :disabled="!hasUrl" @click="toggleExpand">
          {{ expanded ? "收起" : "展开" }}
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.link-source-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-card);
}

.link-source-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.link-source-card__label {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.link-source-card__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.link-source-card__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}

.link-source-card__grid dt {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.link-source-card__grid dd {
  margin-top: 4px;
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-source-card__url {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 40px;
  padding: 8px 10px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-input);
}

.link-source-card__url-text {
  overflow: hidden;
  color: var(--color-text-secondary);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-source-card__url-empty {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.link-source-card__actions {
  display: flex;
  gap: 6px;
  flex: none;
}

.link-source-card__actions button {
  height: 26px;
  padding: 0 10px;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  cursor: pointer;
}

.link-source-card__actions button:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.link-source-card__actions button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
