<script setup lang="ts">
import { computed, ref, watch } from "vue"
import {
  ElButton,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
  ElSwitch
} from "element-plus"
import type { RuleSet } from "@/app/stores/rule"
import type { PriceRuleInput } from "@/widgets/rule-simulator/simulator"

export interface RuleDraftPayload {
  category: string
  ruleSetId: string | null
  data: Record<string, unknown>
}

export interface RulePublishPayload {
  category: string
  ruleSetId: string
  data: Record<string, unknown>
}

interface MaterialRuleRow {
  key: string
  min: number
  max: number
  strategy: string
  baseGroupCount: number
  copyCount: number
  groupSizeCap: number
  targetProjectCount: number
}

const props = defineProps<{
  category: string
  ruleSets: RuleSet[]
  busy?: boolean
  priceRules?: PriceRuleInput[]
  cids?: Record<string, unknown>[]
  adPresets?: Record<string, unknown>[]
  openPresets?: Record<string, unknown>[]
  accounts?: Record<string, unknown>[]
  mappingProposal?: Record<string, unknown>[]
  deliveryLoading?: boolean
}>()

const emit = defineEmits<{
  (e: "update:priceRules", rules: PriceRuleInput[]): void
  (e: "saveDraft", payload: RuleDraftPayload): void
  (e: "publish", payload: RulePublishPayload): void
}>()

const CATEGORY_LABEL: Record<string, string> = {
  link: "链接规则",
  price: "价格模板",
  material: "素材规则",
  account: "账户数据",
  cid: "CID预设",
  adPreset: "广告预设",
  openPreset: "开户预设",
  douyin: "抖音号",
  platform: "平台资源",
  naming: "任务命名",
  runtime: "运行参数",
  version: "版本管理"
}

const RESERVED_ITEMS: Record<string, string[]> = {
  link: ["IAA 选集阈值", "IAP 模板区间", "同距离策略"],
  account: ["飞书账户实时读取", "账户块分配控制", "同步状态"],
  cid: ["CID", "广告预设", "抖音号", "开户预设", "主体", "投放类型", "生效时间"],
  douyin: ["抖音号列表", "启用状态"],
  platform: ["平台域名", "页面路径", "紧急选择器覆盖"],
  naming: ["端付命名模板", "端免命名模板", "测试命名模板"],
  runtime: ["轮询间隔", "轮询超时", "重试次数"]
}

const PRICE_KEYS = [
  { key: "iap_2_9", label: "2.9" },
  { key: "iap_9_9", label: "9.9" }
]

const DEFAULT_PRICE: Record<
  string,
  Omit<PriceRuleInput, "key">
> = {
  iap_2_9: {
    name: "IAP 2.9",
    targetPrice: 2.9,
    minPrice: 2.6,
    maxPrice: 5,
    sameDistanceStrategy: "HIGHER_PRICE_FIRST",
    enabled: true
  },
  iap_9_9: {
    name: "IAP 9.9",
    targetPrice: 9.9,
    minPrice: 8.8,
    maxPrice: 13.8,
    sameDistanceStrategy: "HIGHER_PRICE_FIRST",
    enabled: true
  }
}

const PRICE_STRATEGY_OPTIONS = [
  { value: "HIGHER_PRICE_FIRST", label: "同距离优先高价" },
  { value: "LOWER_PRICE_FIRST", label: "同距离优先低价" }
]

const MATERIAL_STRATEGY_OPTIONS = [
  { value: "BASE_1_COPY_2", label: "基础1组复制2次" },
  { value: "BASE_2_COPY_2", label: "基础2组复制2次" },
  { value: "BASE_3_COPY_1", label: "基础3组复制1次" },
  { value: "EVEN_SPLIT", label: "均匀拆分" }
]

const selectedPriceKey = ref("iap_2_9")
const draft = ref<PriceRuleInput>({
  key: selectedPriceKey.value,
  ...DEFAULT_PRICE[selectedPriceKey.value]
})

watch(
  () => [props.priceRules, selectedPriceKey.value] as const,
  () => {
    const rule = props.priceRules?.find(
      (item) => item.key === selectedPriceKey.value
    )
    if (rule) draft.value = { ...rule }
  },
  { immediate: true }
)

function selectPriceKey(key: string) {
  selectedPriceKey.value = key
}

function pushDraft() {
  const next = { ...draft.value }
  const current = props.priceRules ?? []
  const list =
    current.length > 0
      ? current.map((rule) => (rule.key === next.key ? { ...next } : rule))
      : PRICE_KEYS.map((item) => ({
          key: item.key,
          ...DEFAULT_PRICE[item.key]
        })).map((rule) => (rule.key === next.key ? { ...next } : rule))
  emit("update:priceRules", list)
}

const materialRows = ref<MaterialRuleRow[]>([
  {
    key: "n_leq_30",
    min: 0,
    max: 30,
    strategy: "BASE_1_COPY_2",
    baseGroupCount: 1,
    copyCount: 2,
    groupSizeCap: 30,
    targetProjectCount: 3
  },
  {
    key: "n_30_60",
    min: 31,
    max: 60,
    strategy: "BASE_2_COPY_2",
    baseGroupCount: 2,
    copyCount: 2,
    groupSizeCap: 30,
    targetProjectCount: 3
  }
])

const categoryLabel = computed(
  () => CATEGORY_LABEL[props.category] ?? props.category
)

const ruleSetId = computed(
  () =>
    props.ruleSets.find((rule) => rule.category === categoryLabel.value)?.id ??
    null
)

const isPrice = computed(() => props.category === "price")
const isMaterial = computed(() => props.category === "material")
const isCid = computed(() => props.category === "cid")
const isAdPreset = computed(() => props.category === "adPreset")
const isOpenPreset = computed(() => props.category === "openPreset")
const isDouyin = computed(() => props.category === "douyin")
const isVersion = computed(() => props.category === "version")
const reservedItems = computed(() => RESERVED_ITEMS[props.category] ?? [])

function draftData(): Record<string, unknown> {
  if (isPrice.value) return { ...draft.value }
  if (isMaterial.value) return { ranges: materialRows.value }
  return {}
}

function joinCandidates(value: unknown): string {
  return Array.isArray(value) ? (value as string[]).join("；") : String(value ?? "")
}

function saveDraft() {
  emit("saveDraft", {
    category: categoryLabel.value,
    ruleSetId: ruleSetId.value,
    data: draftData()
  })
}

function publish() {
  if (!ruleSetId.value) return
  emit("publish", {
    category: categoryLabel.value,
    ruleSetId: ruleSetId.value,
    data: draftData()
  })
}
</script>

<template>
  <section class="rule-editor" :aria-label="categoryLabel">
    <header class="rule-editor__header">
      <div>
        <h2 class="rule-editor__title">{{ categoryLabel }}</h2>
        <p class="rule-editor__subtitle">
          {{
            isPrice
              ? "IAP 价格模板与启用状态"
              : isMaterial
                ? "素材数量区间与分组策略"
                : "规则配置结构"
          }}
        </p>
      </div>
    </header>

    <template v-if="isPrice">
      <div class="rule-editor__segmented" role="tablist" aria-label="价格档位">
        <button
          v-for="item in PRICE_KEYS"
          :key="item.key"
          type="button"
          role="tab"
          class="rule-editor__segment"
          :class="{ 'is-active': selectedPriceKey === item.key }"
          @click="selectPriceKey(item.key)"
        >
          {{ item.label }}
        </button>
      </div>

      <div class="rule-editor__form">
        <label class="rule-editor__field">
          <span>规则名称</span>
          <ElInput
            v-model="draft.name"
            placeholder="规则名称"
            @change="pushDraft"
          />
        </label>
        <label class="rule-editor__field">
          <span>目标价格（元）</span>
          <ElInputNumber
            v-model="draft.targetPrice"
            :min="0"
            :step="0.1"
            :precision="2"
            controls-position="right"
            @change="pushDraft"
          />
        </label>
        <label class="rule-editor__field">
          <span>最低价格（元）</span>
          <ElInputNumber
            v-model="draft.minPrice"
            :min="0"
            :step="0.1"
            :precision="2"
            controls-position="right"
            @change="pushDraft"
          />
        </label>
        <label class="rule-editor__field">
          <span>最高价格（元）</span>
          <ElInputNumber
            v-model="draft.maxPrice"
            :min="0"
            :step="0.1"
            :precision="2"
            controls-position="right"
            @change="pushDraft"
          />
        </label>
        <label class="rule-editor__field">
          <span>同距离策略</span>
          <ElSelect
            v-model="draft.sameDistanceStrategy"
            @change="pushDraft"
          >
            <ElOption
              v-for="option in PRICE_STRATEGY_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </ElSelect>
        </label>
        <label class="rule-editor__field rule-editor__field--switch">
          <span>启用状态</span>
          <ElSwitch
            v-model="draft.enabled"
            active-text="启用"
            inactive-text="停用"
            @change="pushDraft"
          />
        </label>
      </div>
    </template>

    <template v-else-if="isMaterial">
      <div class="rule-editor__scroll">
        <table class="rule-editor__table">
          <thead>
            <tr>
              <th>最小素材数</th>
              <th>最大素材数</th>
              <th>分组策略</th>
              <th>基础组数</th>
              <th>复制次数</th>
              <th>单组上限</th>
              <th>目标项目数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in materialRows" :key="row.key">
              <td>
                <ElInputNumber
                  v-model="row.min"
                  :min="0"
                  controls-position="right"
                />
              </td>
              <td>
                <ElInputNumber
                  v-model="row.max"
                  :min="0"
                  :max="9999"
                  controls-position="right"
                />
              </td>
              <td>
                <ElSelect v-model="row.strategy">
                  <ElOption
                    v-for="option in MATERIAL_STRATEGY_OPTIONS"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </ElSelect>
              </td>
              <td>
                <ElInputNumber
                  v-model="row.baseGroupCount"
                  :min="1"
                  controls-position="right"
                />
              </td>
              <td>
                <ElInputNumber
                  v-model="row.copyCount"
                  :min="0"
                  controls-position="right"
                />
              </td>
              <td>
                <ElInputNumber
                  v-model="row.groupSizeCap"
                  :min="1"
                  controls-position="right"
                />
              </td>
              <td>
                <ElInputNumber
                  v-model="row.targetProjectCount"
                  :min="1"
                  controls-position="right"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="isCid">
      <div class="rule-editor__sync-line">
        <span>已同步 CID 组 {{ mappingProposal?.length ?? 0 }} 个</span>
        <span v-if="deliveryLoading" class="rule-editor__sync-status">同步中</span>
      </div>
      <div class="rule-editor__scroll">
        <table class="rule-editor__table">
          <thead>
            <tr>
              <th>CID</th>
              <th>组</th>
              <th>主体</th>
              <th>账户数</th>
              <th>广告预设</th>
              <th>开户预设</th>
              <th>抖音号</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in mappingProposal ?? []"
              :key="String(row.cid)"
            >
              <td>{{ row.cid }}</td>
              <td>{{ row.group }}</td>
              <td>{{ row.company }}</td>
              <td>{{ row.account_count }}</td>
              <td>{{ row.ad_preset }}</td>
              <td>{{ row.open_preset }}</td>
              <td>{{ row.douyin_account || "待配置" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="isAdPreset">
      <div class="rule-editor__sync-line">
        <span>广告预设 {{ adPresets?.length ?? 0 }} 条</span>
        <span v-if="deliveryLoading" class="rule-editor__sync-status">同步中</span>
      </div>
      <div class="rule-editor__scroll">
        <table class="rule-editor__table">
          <thead>
            <tr>
              <th>预设名称</th>
              <th>投放方式</th>
              <th>推广业务</th>
              <th>商品类型</th>
              <th>优化目标</th>
              <th>深度优化</th>
              <th>竞价策略</th>
              <th>ROI系数</th>
              <th>日预算</th>
              <th>模板ID</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in adPresets ?? []" :key="String(row.id)">
              <td>{{ row.preview_name }}</td>
              <td>{{ row.delivery_way }}</td>
              <td>{{ row.promotion_type }}</td>
              <td>{{ row.product_type }}</td>
              <td>{{ row.optimization_target }}</td>
              <td>{{ row.deep_optimization }}</td>
              <td>{{ row.bidding_strategy }}</td>
              <td>{{ row.roi_coefficient }}</td>
              <td>{{ row.daily_budget }}</td>
              <td>{{ row.product_template_id }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="isOpenPreset">
      <div class="rule-editor__sync-line">
        <span>开户预设 {{ openPresets?.length ?? 0 }} 条</span>
        <span v-if="deliveryLoading" class="rule-editor__sync-status">同步中</span>
      </div>
      <div class="rule-editor__scroll">
        <table class="rule-editor__table">
          <thead>
            <tr>
              <th>预设名称</th>
              <th>主体</th>
              <th>变现类型</th>
              <th>App类型</th>
              <th>平台</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in openPresets ?? []" :key="String(row.id)">
              <td>{{ row.preset_name }}</td>
              <td>{{ row.company }}</td>
              <td>{{ row.monetization_type }}</td>
              <td>{{ row.app_type }}</td>
              <td>{{ row.platform }}</td>
              <td>{{ row.created_at }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="isDouyin">
      <p class="rule-editor__note">
        投放系统页面未直接提供抖音号字段；当前可查看账户池，
        待确认抖音号来源后接入映射。
      </p>
      <div class="rule-editor__sync-line">
        <span>账户 {{ accounts?.length ?? 0 }} 条</span>
        <span v-if="deliveryLoading" class="rule-editor__sync-status">同步中</span>
      </div>
    </template>

    <template v-else-if="isVersion">
      <p class="rule-editor__note">
        选择左侧规则分类后，在此查看对应规则集的草稿、校验与发布版本。
      </p>
    </template>

    <template v-else>
      <ul class="rule-editor__reserved">
        <li v-for="item in reservedItems" :key="item" class="rule-editor__reserved-item">
          <span>{{ item }}</span>
          <span class="rule-editor__reserved-status">预留</span>
        </li>
      </ul>
      <p class="rule-editor__note">该分类的配置接口将在后续阶段接入。</p>
    </template>

    <footer
      v-if="isPrice || isMaterial"
      class="rule-editor__actions"
    >
      <ElButton :loading="busy" @click="saveDraft">保存草稿</ElButton>
      <ElButton
        type="primary"
        :disabled="!ruleSetId"
        :loading="busy"
        @click="publish"
      >
        发布版本
      </ElButton>
    </footer>
  </section>
</template>

<style scoped>
.rule-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.rule-editor__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.rule-editor__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-editor__segmented {
  display: inline-flex;
  padding: 3px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-button);
}

.rule-editor__segment {
  min-width: 64px;
  height: 28px;
  padding: 0 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  cursor: pointer;
}

.rule-editor__segment.is-active {
  background: var(--color-bg-panel);
  color: var(--color-primary);
  font-weight: 600;
  box-shadow: 0 1px 3px rgb(30 36 48 / 8%);
}

.rule-editor__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.rule-editor__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.rule-editor__field > span {
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.rule-editor__field :deep(.el-input-number) {
  width: 100%;
}

.rule-editor__field--switch {
  justify-content: flex-end;
}

.rule-editor__scroll {
  overflow-x: auto;
}

.rule-editor__table {
  width: 100%;
  min-width: 1200px;
  border-collapse: collapse;
  font-size: var(--font-size-table);
}

.rule-editor__sync-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.rule-editor__sync-status {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-editor__table th {
  padding: 8px 10px;
  color: var(--color-text-secondary);
  background: var(--color-bg-panel-secondary);
  font-size: var(--font-size-caption);
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #eef0f3;
}

.rule-editor__table td {
  padding: 8px 10px;
  border-bottom: 1px solid #f0f1f3;
}

.rule-editor__table :deep(.el-input-number) {
  width: 110px;
}

.rule-editor__table :deep(.el-select) {
  width: 150px;
}

.rule-editor__reserved {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
}

.rule-editor__reserved-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
}

.rule-editor__reserved-status {
  flex: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-editor__note {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
  line-height: 1.6;
}

.rule-editor__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid #f0f1f3;
}

@media (max-width: 900px) {
  .rule-editor__form {
    grid-template-columns: 1fr;
  }
}
</style>
