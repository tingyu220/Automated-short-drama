<script setup lang="ts">
import { computed } from "vue"
import { ElDropdown, ElDropdownItem, ElDropdownMenu } from "element-plus"
import type { TaskAction, TaskView } from "@/entities/task/types"

const props = withDefaults(
  defineProps<{
    task: TaskView
    disabled?: TaskAction[]
  }>(),
  {
    disabled: () => []
  }
)

const emit = defineEmits<{
  (e: "command", payload: { task: TaskView; action: TaskAction }): void
}>()

const items: Array<{ action: TaskAction; label: string; danger: boolean }> = [
  { action: "manual_enqueue", label: "手动入队", danger: false },
  { action: "pause", label: "暂停", danger: true },
  { action: "resume", label: "恢复", danger: false },
  { action: "retry", label: "重试当前步骤", danger: false },
  { action: "cancel", label: "取消任务", danger: true }
]

const available = computed(() =>
  items.filter((item) => !props.disabled.includes(item.action))
)

function handleCommand(command: string | number | object) {
  emit("command", { task: props.task, action: command as TaskAction })
}
</script>

<template>
  <ElDropdown trigger="click" @command="handleCommand">
    <button class="task-control-menu__trigger" aria-label="更多操作">更多</button>
    <template #dropdown>
      <ElDropdownMenu>
        <ElDropdownItem
          v-for="item in available"
          :key="item.action"
          :command="item.action"
          :class="{ 'is-danger': item.danger }"
        >
          {{ item.label }}
        </ElDropdownItem>
      </ElDropdownMenu>
    </template>
  </ElDropdown>
</template>

<style scoped>
.task-control-menu__trigger {
  height: 28px;
  padding: 0 10px;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-button);
  background: var(--color-bg-panel);
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.task-control-menu__trigger:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

:deep(.is-danger) {
  color: var(--color-status-failed);
}
</style>
