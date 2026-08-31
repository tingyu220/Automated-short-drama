<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ElButton, ElEmpty, ElIcon, ElTag } from "element-plus"
import { Upload } from "@element-plus/icons-vue"
import type { ImportedDramaRecord } from "@/entities/drama-import/types"
import { getPlatformLabel } from "@/shared/utils/status"

const props = withDefaults(defineProps<{
  rows: ImportedDramaRecord[]
  loading: boolean
}>(), { rows: () => [], loading: false })

const emit = defineEmits<{ (event: "enqueue", taskIds: string[]): void }>()
const selectedKeys = ref<string[]>([])
const executableRows = computed(() => props.rows.filter((row) => row.task_id))
const selectedTaskIds = computed(() => props.rows
  .filter((row) => selectedKeys.value.includes(row.source_key) && row.task_id)
  .map((row) => row.task_id as string))
const allSelected = computed(() => executableRows.value.length > 0 && selectedTaskIds.value.length === executableRows.value.length)

watch(() => props.rows, () => {
  selectedKeys.value = selectedKeys.value.filter((key) => props.rows.some((row) => row.source_key === key && row.task_id))
}, { deep: true })

function toggleAll(checked: boolean) {
  selectedKeys.value = checked ? executableRows.value.map((row) => row.source_key) : []
}
</script>

<template>
  <section class="imported-drama" aria-label="当日导入剧目">
    <header class="imported-drama__header">
      <div>
        <h2>当日导入剧目</h2>
        <span>{{ selectedTaskIds.length ? `已选择 ${selectedTaskIds.length} 部` : `共 ${rows.length} 部` }}</span>
      </div>
      <ElButton type="primary" :disabled="!selectedTaskIds.length" :loading="loading" @click="emit('enqueue', selectedTaskIds)">
        <ElIcon><Upload /></ElIcon>搭建所选剧目
      </ElButton>
    </header>
    <div v-if="rows.length" class="imported-drama__table-wrap">
      <table class="imported-drama__table">
        <thead><tr>
          <th><input type="checkbox" aria-label="全选可搭建剧目" :checked="allSelected" @change="toggleAll(($event.target as HTMLInputElement).checked)"></th>
          <th>投放时间</th><th>剧名</th><th>平台</th><th>投手</th><th>状态</th>
        </tr></thead>
        <tbody><tr v-for="row in rows" :key="row.source_key">
          <td><input v-model="selectedKeys" type="checkbox" :value="row.source_key" :disabled="!row.task_id" :aria-label="`选择${row.drama_name}`"></td>
          <td>{{ row.available_time }}</td><td>{{ row.drama_name }}</td><td>{{ getPlatformLabel(row.platform) }}</td><td>{{ row.operator_name }}</td>
          <td>
            <ElTag
              size="small"
              :type="row.task_id ? 'info' : 'warning'"
              :title="row.task_id ? undefined : '导入记录已保存，等待调度器创建本地任务'"
            >{{ row.task_id ? row.task_status : "待关联任务" }}</ElTag>
          </td>
        </tr></tbody>
      </table>
    </div>
    <ElEmpty v-else description="当天还没有已确认导入的剧目" :image-size="64" />
  </section>
</template>

<style scoped>
.imported-drama { border: 1px solid #e5e7eb; border-radius: var(--radius-panel); background: var(--color-bg-panel); }
.imported-drama__header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 14px; border-bottom:1px solid #e5e7eb; }
.imported-drama__header h2 { margin:0; color:var(--color-text-primary); font-size:16px; font-weight:600; }
.imported-drama__header span { color:var(--color-text-tertiary); font-size:13px; }
.imported-drama__table-wrap { overflow:auto; }
.imported-drama__table { width:100%; min-width:760px; border-collapse:collapse; text-align:left; font-size:13px; }
.imported-drama__table th,.imported-drama__table td { padding:11px 14px; border-bottom:1px solid #eef0f3; white-space:nowrap; }
.imported-drama__table th { color:var(--color-text-secondary); font-weight:500; background:#f8fafc; }
.imported-drama__table th:first-child,.imported-drama__table td:first-child { width:42px; text-align:center; }
.imported-drama__table tr:last-child td { border-bottom:0; }
@media (max-width:720px) { .imported-drama__header { align-items:flex-start; flex-direction:column; } .imported-drama__header :deep(.el-button) { width:100%; } }
</style>
