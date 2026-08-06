<script setup lang="ts">
import { onMounted } from "vue"
import { ElButton, ElMessage } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import ExceptionPanel, {
  type ExceptionAction
} from "@/features/exception-resolution/ExceptionPanel.vue"
import { useExceptionStore, type ExceptionItem } from "@/app/stores/exception"
import { useRouter } from "vue-router"

const exceptionStore = useExceptionStore()
const router = useRouter()

async function load() {
  await exceptionStore.fetchExceptions()
}

onMounted(load)

function handleAction(payload: { item: ExceptionItem; action: ExceptionAction }) {
  if (payload.action === "modify_config") {
    void router.push("/rules")
    return
  }
  ElMessage.info("该操作 V1 待接入后端")
}
</script>

<template>
  <div class="exceptions-page">
    <header class="exceptions-page__header">
      <div>
        <h1 class="exceptions-page__title">异常中心</h1>
        <p class="exceptions-page__subtitle">
          登录失效、配置缺失、页面变化、结果不确定与部分写入
        </p>
      </div>
      <ElButton :loading="exceptionStore.loading" @click="load">
        <el-icon><Refresh /></el-icon>
        刷新
      </ElButton>
    </header>

    <ExceptionPanel
      :items="exceptionStore.exceptions"
      :loading="exceptionStore.loading"
      :error="exceptionStore.error"
      @retry="load"
      @action="handleAction"
    />
  </div>
</template>

<style scoped>
.exceptions-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.exceptions-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.exceptions-page__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.exceptions-page__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}
</style>
