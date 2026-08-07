<script setup lang="ts">
import { useRouter } from "vue-router"
import { ArrowLeft } from "@element-plus/icons-vue"

const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    backTo?: string
    showBack?: boolean
  }>(),
  {
    subtitle: "",
    backTo: "/",
    showBack: true
  }
)

const router = useRouter()

function goBack() {
  void router.push(props.backTo)
}
</script>

<template>
  <header class="page-header">
    <div class="page-header__left">
      <button
        v-if="showBack"
        type="button"
        class="page-header__back"
        :title="'返回工作台'"
        @click="goBack"
      >
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <div>
        <h1 class="page-header__title">{{ title }}</h1>
        <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div class="page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header__left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.page-header__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: var(--color-bg-panel);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  flex-shrink: 0;
}

.page-header__back:hover {
  background: var(--color-bg-page);
  color: var(--color-text-primary);
}

.page-header__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
  white-space: nowrap;
}

.page-header__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
</style>
