<script setup lang="ts">
import { RouterLink } from "vue-router"
import type { Component } from "vue"

withDefaults(
  defineProps<{
    title: string
    value: string | number
    icon?: Component
    desc?: string
    to?: string
  }>(),
  {
    icon: undefined,
    desc: "",
    to: ""
  }
)
</script>

<template>
  <div class="metric-card">
    <div class="metric-card__header">
      <span class="metric-card__title">{{ title }}</span>
      <span v-if="icon" class="metric-card__icon">
        <component :is="icon" />
      </span>
    </div>
    <div class="metric-card__value">{{ value }}</div>
    <div class="metric-card__footer">
      <span v-if="desc" class="metric-card__desc">{{ desc }}</span>
      <RouterLink v-if="to" class="metric-card__link" :to="to">查看</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.metric-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 112px;
  padding: 20px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
}

.metric-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.metric-card__title {
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  font-weight: 500;
}

.metric-card__icon {
  display: inline-flex;
  color: var(--color-primary);
  font-size: 18px;
}

.metric-card__value {
  color: var(--color-text-primary);
  font-size: var(--font-size-key-number);
  font-weight: 600;
  line-height: 1.2;
}

.metric-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.metric-card__desc {
  overflow: hidden;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-card__link {
  flex: none;
  font-size: var(--font-size-caption);
  font-weight: 500;
}
</style>
