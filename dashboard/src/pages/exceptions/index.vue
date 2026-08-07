<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ElButton, ElMessage } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import ExceptionPanel, {
  type ExceptionAction
} from "@/features/exception-resolution/ExceptionPanel.vue"
import PageHeader from "@/shared/ui/PageHeader.vue"
import PaginationBar from "@/shared/ui/PaginationBar.vue"
import { useExceptionStore, type ExceptionItem } from "@/app/stores/exception"
import { useRouter } from "vue-router"

const exceptionStore = useExceptionStore()
const router = useRouter()
const page = ref(1)
const pageSize = ref(10)

const pagedExceptions = computed(() =>
  exceptionStore.exceptions.slice(
    (page.value - 1) * pageSize.value,
    page.value * pageSize.value
  )
)

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
    <PageHeader
      title="异常中心"
      subtitle="登录失效、配置缺失、页面变化、结果不确定与部分写入"
    >
      <template #actions>
        <ElButton :loading="exceptionStore.loading" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </ElButton>
      </template>
    </PageHeader>

    <ExceptionPanel
      :items="pagedExceptions"
      :loading="exceptionStore.loading"
      :error="exceptionStore.error"
      @retry="load"
      @action="handleAction"
    />

    <PaginationBar
      v-model:page="page"
      v-model:page-size="pageSize"
      :total="exceptionStore.exceptions.length"
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
