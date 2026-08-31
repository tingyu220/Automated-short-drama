<script setup lang="ts">
import { watch } from "vue"
import { ElPagination } from "element-plus"

const props = withDefaults(
  defineProps<{
    total: number
    page: number
    pageSize: number
    pageSizes?: number[]
  }>(),
  {
    pageSizes: () => [10, 20, 50]
  }
)

const emit = defineEmits<{
  (e: "update:page", value: number): void
  (e: "update:pageSize", value: number): void
}>()

watch(
  () => props.total,
  () => emit("update:page", 1)
)
</script>

<template>
  <div class="pagination-bar">
    <el-pagination
      background
      :total="total"
      :current-page="page"
      :page-size="pageSize"
      :page-sizes="pageSizes"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="(value: number) => emit('update:page', value)"
      @size-change="(value: number) => emit('update:pageSize', value)"
    />
  </div>
</template>

<style scoped>
.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
}

@media (max-width: 720px) {
  .pagination-bar {
    justify-content: center;
    overflow: hidden;
  }

  .pagination-bar :deep(.el-pagination__total),
  .pagination-bar :deep(.el-pagination__sizes),
  .pagination-bar :deep(.el-pagination__jump) {
    display: none;
  }
}
</style>
