<script setup lang="ts">
</script>

<template>
  <div class="page-placeholder">
    <h1 class="page-placeholder__title">异常中心</h1>
    <p class="page-placeholder__desc">登录失效、配置缺失、页面变化、账户无空位、轮询超时</p>
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
