<script setup lang="ts">
import { ElAlert, ElButton, ElDialog, ElEmpty } from "element-plus"
import type { DramaImportPreview } from "@/entities/drama-import/types"

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    preview: DramaImportPreview | null
    loading: boolean
    error: string | null
  }>(),
  { preview: null, loading: false, error: null }
)

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void
  (event: "confirm"): void
}>()

function close() {
  if (!props.loading) emit("update:modelValue", false)
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    title="读取今日剧目"
    width="min(860px, calc(100vw - 24px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!loading"
    :show-close="!loading"
    @update:model-value="close"
  >
    <div class="drama-import-dialog">
      <ElAlert
        v-if="error"
        type="error"
        :closable="false"
        :title="error"
        show-icon
      />
      <template v-else-if="preview">
        <p class="drama-import-dialog__hint">
          {{ preview.business_date }}（北京时间）公用表预览，确认后新增剧目会插入私有表顶部。
        </p>

        <div class="drama-import-dialog__metrics" aria-label="导入预览统计">
          <div class="drama-import-dialog__metric">
            <span>当日</span><strong>{{ preview.source_count }}</strong>
          </div>
          <div class="drama-import-dialog__metric is-primary">
            <span>新增</span><strong>{{ preview.new_count }}</strong>
          </div>
          <div class="drama-import-dialog__metric">
            <span>重复 {{ preview.duplicate_count }}</span>
          </div>
          <div class="drama-import-dialog__metric" :class="{ 'is-warning': preview.invalid_count }">
            <span>异常 {{ preview.invalid_count }}</span>
          </div>
        </div>

        <div v-if="preview.rows.length" class="drama-import-dialog__table-wrap">
          <table class="drama-import-dialog__table">
            <thead>
              <tr><th>来源行</th><th>剧目</th><th>平台</th><th>上线时间</th><th>链接</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in preview.rows" :key="row.source_row">
                <td>{{ row.source_row }}</td>
                <td>{{ row.drama_name }}</td>
                <td>{{ row.platform }}</td>
                <td>{{ row.available_time }}</td>
                <td>{{ row.has_validated_links ? "可复用" : "待提取" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <ElEmpty v-else description="没有可导入的新增剧目" :image-size="72" />

        <details v-if="preview.errors.length" class="drama-import-dialog__errors" open>
          <summary>查看异常行</summary>
          <ul>
            <li v-for="item in preview.errors" :key="item.source_row">
              第 {{ item.source_row }} 行：{{ item.message }}
            </li>
          </ul>
        </details>
      </template>
      <div v-else class="drama-import-dialog__loading" role="status">正在读取公用表…</div>
    </div>

    <template #footer>
      <ElButton :disabled="loading" @click="close">取消</ElButton>
      <ElButton
        type="primary"
        :loading="loading"
        :disabled="!preview || preview.new_count === 0"
        aria-label="确认导入今日剧目"
        @click="emit('confirm')"
      >
        确认导入
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.drama-import-dialog { display: flex; flex-direction: column; gap: 14px; min-height: 128px; }
.drama-import-dialog__hint { margin: 0; color: var(--color-text-secondary); font-size: var(--font-size-body); line-height: 1.6; }
.drama-import-dialog__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden; }
.drama-import-dialog__metric { display: flex; flex-direction: column; gap: 4px; min-height: 66px; padding: 10px 14px; border-right: 1px solid #e5e7eb; color: var(--color-text-secondary); font-size: 12px; }
.drama-import-dialog__metric:last-child { border-right: 0; }
.drama-import-dialog__metric strong { color: var(--color-text-primary); font-size: 22px; line-height: 1.1; }
.drama-import-dialog__metric.is-primary strong { color: var(--color-primary); }
.drama-import-dialog__metric.is-warning { color: var(--color-warning); }
.drama-import-dialog__metric.is-warning span { color: var(--color-warning); }
.drama-import-dialog__table-wrap { max-height: 320px; overflow: auto; border: 1px solid #e5e7eb; border-radius: 6px; }
.drama-import-dialog__table { width: 100%; min-width: 620px; border-collapse: collapse; font-size: 13px; text-align: left; }
.drama-import-dialog__table th { position: sticky; top: 0; z-index: 1; background: #f8fafc; color: var(--color-text-secondary); font-weight: 500; }
.drama-import-dialog__table th, .drama-import-dialog__table td { padding: 9px 12px; border-bottom: 1px solid #eef0f3; white-space: nowrap; }
.drama-import-dialog__table tr:last-child td { border-bottom: 0; }
.drama-import-dialog__errors { color: var(--color-text-secondary); font-size: 13px; }
.drama-import-dialog__errors summary { color: var(--color-warning); cursor: pointer; }
.drama-import-dialog__errors ul { margin: 8px 0 0; padding-left: 18px; }
.drama-import-dialog__loading { display: grid; min-height: 128px; place-items: center; color: var(--color-text-secondary); }

@media (max-width: 640px) {
  .drama-import-dialog__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .drama-import-dialog__metric:nth-child(2) { border-right: 0; }
  .drama-import-dialog__metric:nth-child(-n + 2) { border-bottom: 1px solid #e5e7eb; }
}
</style>
