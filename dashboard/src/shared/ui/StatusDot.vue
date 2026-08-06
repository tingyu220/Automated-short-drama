<script setup lang="ts">
withDefaults(
  defineProps<{
    color?: string
    active?: boolean
  }>(),
  {
    color: "var(--color-status-pending)",
    active: false
  }
)
</script>

<template>
  <span
    class="status-dot"
    :class="{ 'is-active': active }"
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
