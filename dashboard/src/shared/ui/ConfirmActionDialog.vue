<script setup lang="ts">
import { ElButton, ElDialog } from "element-plus"

withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    content: string
    confirmText?: string
    confirmType?: "primary" | "danger"
    loading?: boolean
  }>(),
  {
    confirmText: "确认",
    confirmType: "primary",
    loading: false
  }
)

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void
  (e: "confirm"): void
  (e: "cancel"): void
}>()

function onUpdate(value: boolean) {
  emit("update:modelValue", value)
  if (!value) {
    emit("cancel")
  }
}

function onConfirm() {
  emit("confirm")
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="title"
    width="420px"
    :close-on-click-modal="false"
    @update:model-value="onUpdate"
  >
    <p class="confirm-dialog__content">{{ content }}</p>
    <template #footer>
      <ElButton @click="onUpdate(false)">取消</ElButton>
      <ElButton :type="confirmType" :loading="loading" @click="onConfirm">
        {{ confirmText }}
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.confirm-dialog__content {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  line-height: 1.6;
}
</style>
