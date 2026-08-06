<script setup lang="ts">
withDefaults(
  defineProps<{
    rows?: number
  }>(),
  {
    rows: 3
  }
)
</script>

<template>
  <div class="loading-skeleton" aria-label="加载中" role="status">
    <div v-for="row in rows" :key="row" class="loading-skeleton__row">
      <span
        class="loading-skeleton__bar"
        :style="{ width: `${Math.max(40, 100 - row * 12)}%` }"
      />
    </div>
  </div>
</template>

<style scoped>
.loading-skeleton {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 0;
}

.loading-skeleton__row {
  display: flex;
}

.loading-skeleton__bar {
  height: 14px;
  background: linear-gradient(
    90deg,
    var(--color-bg-panel-secondary) 25%,
    var(--color-primary-50) 50%,
    var(--color-bg-panel-secondary) 75%
  );
  background-size: 200% 100%;
  border-radius: 4px;
  animation: loading-skeleton-shimmer 1.4s ease-in-out infinite;
}

@keyframes loading-skeleton-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
