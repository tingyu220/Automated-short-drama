<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    description?: string
  }>(),
  {
    title: "暂无数据",
    description: ""
  }
)
</script>

<template>
  <div class="empty-state">
    <div class="empty-state__mark" aria-hidden="true" />
    <p class="empty-state__title">{{ title }}</p>
    <p v-if="description" class="empty-state__description">{{ description }}</p>
    <div v-if="$slots.default" class="empty-state__actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 180px;
  padding: 24px;
  text-align: center;
}

.empty-state__mark {
  width: 36px;
  height: 36px;
  border: 1px dashed var(--color-text-tertiary);
  border-radius: 50%;
}

.empty-state__title {
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  font-weight: 500;
}

.empty-state__description {
  max-width: 420px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
  line-height: 1.6;
}

.empty-state__actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
