<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    color?: string
    active?: boolean | string
  }>(),
  {
    color: "var(--color-status-pending)",
    active: false
  }
)

const isActive = computed(
  () => props.active === true || String(props.active).toLowerCase() === "true"
)
</script>

<template>
  <span
    class="status-dot"
    :class="{ 'is-active': isActive }"
    :style="{ backgroundColor: color }"
    aria-hidden="true"
  />
</template>

<style scoped>
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
}

.status-dot.is-active {
  animation: status-dot-pulse 1.6s ease-in-out infinite;
}

@keyframes status-dot-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>
