<script setup lang="ts">
</script>

<template>
  <div class="page-placeholder">
    <h1 class="page-placeholder__title">今日任务</h1>
    <p class="page-placeholder__desc">当天从飞书同步的剧目任务列表</p>
  </div>
</template>

<style scoped>
.page-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: var(--color-text-tertiary);
}
.page-placeholder__title {
  font-size: var(--font-size-page-title);
  color: var(--color-text-primary);
  margin-bottom: var(--space-8);
}
.page-placeholder__desc {
  font-size: var(--font-size-body);
}
</style>
