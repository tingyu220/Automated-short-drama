<script setup lang="ts">
</script>

<template>
  <div class="page-placeholder">
    <h1 class="page-placeholder__title">自动化队列</h1>
    <p class="page-placeholder__desc">任务执行顺序、Worker 锁、租约与重试状态</p>
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
