<script setup lang="ts">
</script>

<template>
  <div class="page-placeholder">
    <h1 class="page-placeholder__title">规则与配置</h1>
    <p class="page-placeholder__desc">IAA/IAP 规则、素材规则、账户数据、CID 预设、平台资源</p>
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
