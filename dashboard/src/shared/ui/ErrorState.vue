<script setup lang="ts">
import { ElButton } from "element-plus"

withDefaults(
  defineProps<{
    message?: string
    retryText?: string
  }>(),
  {
    message: "请求失败，请稍后重试",
    retryText: "重试"
  }
)

const emit = defineEmits<{
  (e: "retry"): void
}>()
</script>

<template>
  <div class="error-state">
    <div class="error-state__mark" aria-hidden="true">!</div>
    <p class="error-state__message">{{ message }}</p>
    <ElButton size="small" type="primary" @click="emit('retry')">
      {{ retryText }}
    </ElButton>
  </div>
</template>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 180px;
  padding: 24px;
  text-align: center;
}

.error-state__mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: var(--color-status-failed);
  background: color-mix(in srgb, var(--color-status-failed) 12%, transparent);
  border-radius: 50%;
  font-size: 16px;
  font-weight: 600;
}

.error-state__message {
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  line-height: 1.6;
}
</style>
