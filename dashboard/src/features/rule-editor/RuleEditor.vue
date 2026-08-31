<script setup lang="ts">
import { computed, ref, watch } from "vue"
import {
  ElButton,
  ElInput,
  ElInputNumber,
  ElOption,
  ElPagination,
  ElSelect,
  ElSwitch
} from "element-plus"
import type { RuleSet } from "@/app/stores/rule"
import type { MaterialRuleRange } from "@/app/stores/rule"
import type { PriceRuleInput } from "@/widgets/rule-simulator/simulator"
import { paginateRows, validPage } from "./pagination"

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

export interface MappingRow {
  [key: string]: unknown
  cid: string
  group: string
  company: string
  pay_type: string | null
  account_count: number
  ad_preset: string
  open_preset: string
  douyin_account: string
  ad_preset_candidates?: string[]
  open_preset_candidates?: string[]
}

interface PlatformResource {
  platform: string
  status: string
  url: string
}

interface SettingField {
  key: string
  label: string
  type: "input" | "number" | "select"
  options?: string[]
  optionsKey?: string
}

const props = defineProps<{
  category: string
  ruleSets: RuleSet[]
  busy?: boolean
  priceRules?: PriceRuleInput[]
  materialRules?: MaterialRuleRange[]
  cids?: Record<string, unknown>[]
  adPresets?: Record<string, unknown>[]
  openPresets?: Record<string, unknown>[]
  accounts?: Record<string, unknown>[]
  mappingProposal?: MappingRow[]
  deliveryLoading?: boolean
  saving?: boolean
  platformResources?: PlatformResource[]
  settings?: Record<string, Record<string, any>>
  settingsOptions?: Record<string, unknown[]>
  settingsSaving?: boolean
  versions?: { id: string; version: string; status: string; published_at: string | null }[]
}>()

const emit = defineEmits<{
  (e: "update:priceRules", rules: PriceRuleInput[]): void
  (e: "saveDraft", payload: RuleDraftPayload): void
  (e: "publish", payload: RulePublishPayload): void
  (e: "saveMapping", rows: MappingRow[]): void
  (e: "saveSettings", values: Record<string, Record<string, any>>): void
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
  link: ["IAA 选集阈值"],
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

const TASK_NAMING_TEMPLATES = [
  "<平台方>#端付<剧名称><日期>ubr-<创建日期>-<时分秒-n>",
  "<平台方>#端免<剧名称><日期>bxr-<创建日期>-<时分秒-n>",
  "<平台方>#测试<剧名称><日期>cbo-<创建日期>-<时分秒-n>"
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

function addMaterialRule() {
  materialRuleSequence += 1
  materialRows.value.push({
    key: `custom_material_${materialRuleSequence}`,
    min: 0,
    max: 30,
    strategy: "BASE_1_COPY_2",
    baseGroupCount: 1,
    copyCount: 2,
    groupSizeCap: 30,
    targetProjectCount: 3
  })
}

function removeMaterialRule(key: string) {
  materialRows.value = materialRows.value.filter((row) => row.key !== key)
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

const materialRows = ref<MaterialRuleRow[]>([])
let materialRuleSequence = 0

watch(
  () => props.materialRules,
  (rows) => {
    materialRows.value = (rows ?? []).map((row) => ({
      key: row.key,
      min: row.min_material_count,
      max: row.max_material_count ?? 9999,
      strategy: row.strategy,
      baseGroupCount: row.base_group_count,
      copyCount: row.copy_count,
      groupSizeCap: row.group_size_cap,
      targetProjectCount: row.target_project_count
    }))
  },
  { immediate: true }
)

const mappingDraft = ref<MappingRow[]>([])

watch(
  () => props.mappingProposal,
  (rows) => {
    mappingDraft.value = (rows ?? []).map((row) => ({ ...row }))
  },
  { immediate: true }
)

const SETTING_FIELDS: Record<string, SettingField[]> = {
  link: [
    { key: "iaa_episode_threshold", label: "IAA 选集阈值", type: "number" }
  ],
  douyin: [
    {
      key: "douyin_account",
      label: "抖音号",
      type: "select",
      optionsKey: "douyin_accounts"
    }
  ],
  platform: [
    { key: "delivery_base_url", label: "投放系统地址", type: "input" },
    { key: "ocean_base_url", label: "巨量地址", type: "input" },
    { key: "tomato_base_url", label: "番茄地址", type: "input" }
  ],
  naming: [
    {
      key: "iaa_project_template",
      label: "端免项目名模板",
      type: "select",
      options: TASK_NAMING_TEMPLATES
    },
    {
      key: "iap_project_template",
      label: "端付项目名模板",
      type: "select",
      options: TASK_NAMING_TEMPLATES
    },
    {
      key: "test_project_template",
      label: "测试项目名模板",
      type: "select",
      options: TASK_NAMING_TEMPLATES
    }
  ],
  runtime: [
    { key: "scan_interval_seconds", label: "扫描间隔（秒）", type: "number" },
    { key: "login_wait_seconds", label: "登录等待（秒）", type: "number" },
    { key: "price_tiers", label: "价格档位", type: "input" },
    { key: "material_group_cap", label: "单素材组上限", type: "number" },
    { key: "max_project_count", label: "最大项目数", type: "number" }
  ],
  account: [
    {
      key: "account_owner",
      label: "账户归属",
      type: "select",
      optionsKey: "account_owners"
    },
    {
      key: "test_account_source",
      label: "测试户来源",
      type: "select",
      options: ["IAA_B4", "TEST_TABLE"]
    }
  ]
}

const categoryLabel = computed(
  () => CATEGORY_LABEL[props.category] ?? props.category
)

const settingsDraft = ref<Record<string, any>>({})

watch(
  () => [props.settings, props.category] as const,
  () => {
    settingsDraft.value = {
      ...((props.settings ?? {})[props.category] ?? {})
    }
  },
  { immediate: true }
)

const settingFields = computed(() => SETTING_FIELDS[props.category] ?? [])

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
const isLink = computed(() => props.category === "link")
const isAccount = computed(() => props.category === "account")
const isPlatform = computed(() => props.category === "platform")
const isNaming = computed(() => props.category === "naming")
const isRuntime = computed(() => props.category === "runtime")
const isVersion = computed(() => props.category === "version")
const reservedItems = computed(() => RESERVED_ITEMS[props.category] ?? [])

const currentPublishedVersion = computed(() => {
  const versions = props.versions ?? []
  return versions.find((v) => v.status === "PUBLISHED") ?? null
})

const pendingDraftVersion = computed(() => {
  const versions = props.versions ?? []
  return versions.find((v) => v.status === "DRAFT" || v.status === "VALIDATING") ?? null
})
const tablePage = ref(1)
const tablePageSize = ref(10)

const tableRowCount = computed(() => {
  if (isMaterial.value) return materialRows.value.length
  if (isCid.value) return mappingDraft.value.length
  if (isAdPreset.value) return props.adPresets?.length ?? 0
  if (isOpenPreset.value) return props.openPresets?.length ?? 0
  if (isVersion.value) return props.ruleSets.length
  return 0
})
const pagedMaterialRows = computed(() =>
  paginateRows(materialRows.value, tablePage.value, tablePageSize.value)
)
const pagedMappingRows = computed(() =>
  paginateRows(mappingDraft.value, tablePage.value, tablePageSize.value)
)
const pagedAdPresets = computed(() =>
  paginateRows(props.adPresets ?? [], tablePage.value, tablePageSize.value)
)
const pagedOpenPresets = computed(() =>
  paginateRows(props.openPresets ?? [], tablePage.value, tablePageSize.value)
)
const pagedRuleSets = computed(() =>
  paginateRows(props.ruleSets, tablePage.value, tablePageSize.value)
)
const hasPagedTable = computed(
  () => isMaterial.value || isCid.value || isAdPreset.value || isOpenPreset.value || isVersion.value
)

watch(
  () => [props.category, tablePageSize.value] as const,
  () => { tablePage.value = 1 }
)
watch(tableRowCount, (total) => {
  tablePage.value = validPage(total, tablePage.value, tablePageSize.value)
})

const runtimeRows = [
  { name: "剧目扫描间隔", value: "3600 秒（每小时）" },
  { name: "登录等待超时", value: "600 秒（10 分钟）" },
  { name: "价格档位", value: "2.9 / 9.9 两档" },
  {
    name: "素材分组区间",
    value: "0-30 / 31-60 两档，测试户另计"
  }
]

const douyinAccounts = computed(() => {
  const values = new Set<string>()
  for (const row of mappingDraft.value) {
    const value = String(row.douyin_account || "").trim()
    if (value) values.add(value)
  }
  return [...values]
})

const accountStats = computed(() => {
  const accounts = props.accounts ?? []
  const companies = new Set<string>()
  const payTypes = new Map<string, number>()
  for (const account of accounts) {
    const company = String(account.oceanCompanyName || "").trim()
    if (company) companies.add(company)
    const pay = String(account.payType || "未知")
    payTypes.set(pay, (payTypes.get(pay) ?? 0) + 1)
  }
  return {
    count: accounts.length,
    companies: companies.size,
    payTypes: [...payTypes.entries()]
  }
})

function draftData(): Record<string, unknown> {
  if (isPrice.value) {
    return {
      price_rules:
        props.priceRules && props.priceRules.length > 0
          ? props.priceRules
          : [{ ...draft.value }]
    }
  }
  if (isMaterial.value) return { ranges: materialRows.value }
  return {}
}

function joinCandidates(value: unknown): string {
  return Array.isArray(value) ? (value as string[]).join("；") : String(value ?? "")
}

function saveMapping() {
  emit("saveMapping", mappingDraft.value)
}

function fieldOptions(field: SettingField): string[] {
  if (field.options) return field.options
  if (field.optionsKey) {
    return (props.settingsOptions?.[field.optionsKey] ?? []).map(String)
  }
  return []
}

function mappingOptions(row: MappingRow, key: "ad_preset" | "open_preset" | "douyin_account") {
  const candidateKey = `${key}_candidates`
  const rowOptions = Array.isArray(row[candidateKey]) ? row[candidateKey] : []
  const globalKey = key === "douyin_account" ? "douyin_accounts" : candidateKey
  const globalOptions = props.settingsOptions?.[globalKey] ?? []
  return [...new Set([...rowOptions, ...globalOptions].map(String).filter(Boolean))]
}

function saveSettingsForm() {
  emit("saveSettings", { [props.category]: settingsDraft.value })
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
      <div class="rule-editor__sync-line">
        <span>素材分组区间</span>
        <ElButton data-test="add-material-rule" size="small" @click="addMaterialRule">
          新增区间
        </ElButton>
      </div>
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
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in pagedMaterialRows" :key="row.key">
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
              <td>
                <ElButton size="small" text type="danger" @click="removeMaterialRule(row.key)">
                  删除
                </ElButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="isCid">
      <div class="rule-editor__sync-line">
        <span>已同步 CID 组 {{ mappingDraft.length }} 个</span>
        <span v-if="deliveryLoading" class="rule-editor__sync-status">同步中</span>
        <ElButton
          type="primary"
          size="small"
          :loading="saving"
          @click="saveMapping"
        >
          保存修改
        </ElButton>
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
            <tr v-for="row in pagedMappingRows" :key="row.cid">
              <td>{{ row.cid }}</td>
              <td>{{ row.group }}</td>
              <td>{{ row.company }}</td>
              <td>{{ row.account_count }}</td>
              <td>
                <ElSelect v-model="row.ad_preset" filterable allow-create default-first-option>
                  <ElOption v-for="option in mappingOptions(row, 'ad_preset')" :key="option" :label="option" :value="option" />
                </ElSelect>
                <p class="rule-editor__candidate-hint">可选：{{ mappingOptions(row, "ad_preset").join("、") || "无，可直接输入" }}</p>
              </td>
              <td>
                <ElSelect v-model="row.open_preset" filterable allow-create default-first-option>
                  <ElOption v-for="option in mappingOptions(row, 'open_preset')" :key="option" :label="option" :value="option" />
                </ElSelect>
                <p class="rule-editor__candidate-hint">可选：{{ mappingOptions(row, "open_preset").join("、") || "无，可直接输入" }}</p>
              </td>
              <td>
                <ElSelect v-model="row.douyin_account" filterable allow-create default-first-option>
                  <ElOption v-for="option in mappingOptions(row, 'douyin_account')" :key="option" :label="option" :value="option" />
                </ElSelect>
                <p class="rule-editor__candidate-hint">可选：{{ mappingOptions(row, "douyin_account").join("、") || "无，可直接输入" }}</p>
              </td>
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
            <tr v-for="row in pagedAdPresets" :key="String(row.id)">
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
            <tr v-for="row in pagedOpenPresets" :key="String(row.id)">
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

    <template
      v-else-if="
        isDouyin ||
        isLink ||
        isAccount ||
        isPlatform ||
        isNaming ||
        isRuntime
      "
    >
      <div class="rule-editor__sync-line">
        <span>{{ categoryLabel }} 配置</span>
        <span v-if="deliveryLoading" class="rule-editor__sync-status">同步中</span>
        <ElButton
          type="primary"
          size="small"
          :loading="settingsSaving"
          @click="saveSettingsForm"
        >
          保存修改
        </ElButton>
      </div>
      <div class="rule-editor__form">
        <label
          v-for="field in settingFields"
          :key="field.key"
          class="rule-editor__field"
        >
          <span>{{ field.label }}</span>
          <ElInputNumber
            v-if="field.type === 'number'"
            v-model="settingsDraft[field.key]"
            :min="0"
            controls-position="right"
          />
          <ElSelect
            v-else-if="field.type === 'select'"
            v-model="settingsDraft[field.key]"
            filterable
            allow-create
            default-first-option
          >
            <ElOption
              v-for="option in fieldOptions(field)"
              :key="option"
              :label="option"
              :value="option"
            />
          </ElSelect>
          <ElInput v-else v-model="settingsDraft[field.key]" />
        </label>
      </div>
    </template>

    <template v-else-if="isVersion">
      <div class="rule-editor__version-info">
        <p class="rule-editor__version-info-text">
          共 {{ ruleSets.length }} 个规则集。请在下方选择规则集查看版本历史、校验和发布。
        </p>
        <div class="rule-editor__version-summary">
          <div v-for="rs in ruleSets" :key="rs.id" class="rule-editor__version-summary-item">
            <span class="rule-editor__version-summary-name">{{ rs.name }}</span>
            <span class="rule-editor__version-summary-cat">{{ rs.category }}</span>
            <span class="rule-editor__version-summary-status" :class="rs.status === 'ACTIVE' ? 'is-active' : ''">
              {{ rs.status }}
            </span>
          </div>
        </div>
      </div>
    </template>

    <div v-if="hasPagedTable" class="rule-editor__pagination">
      <span>共 {{ tableRowCount }} 条</span>
      <ElPagination
        v-model:current-page="tablePage"
        v-model:page-size="tablePageSize"
        :total="tableRowCount"
        :page-sizes="[10, 20, 50]"
        layout="sizes, prev, pager, next"
      />
    </div>

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
      <div class="rule-editor__version-status">
        <span v-if="currentPublishedVersion" class="rule-editor__version-badge rule-editor__version-badge--published">
          当前生效: v{{ currentPublishedVersion.version }}
        </span>
        <span v-if="pendingDraftVersion" class="rule-editor__version-badge rule-editor__version-badge--draft">
          有草稿: v{{ pendingDraftVersion.version }} 未发布
        </span>
        <span v-if="!currentPublishedVersion && !pendingDraftVersion" class="rule-editor__version-badge rule-editor__version-badge--none">
          暂无版本
        </span>
      </div>
      <div class="rule-editor__action-buttons">
        <ElButton
          :loading="busy"
          :disabled="!ruleSetId"
          @click="saveDraft"
        >
          保存草稿
        </ElButton>
        <ElButton
          type="primary"
          :disabled="!ruleSetId"
          :loading="busy"
          @click="publish"
        >
          发布版本
        </ElButton>
      </div>
    </footer>
    <p v-if="isMaterial && !ruleSetId" class="rule-editor__note">
      素材规则暂无对应规则集，当前仅展示生效规则，暂不可保存或发布。
    </p>
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
  max-height: 520px;
  overflow-x: auto;
  overflow-y: auto;
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

.rule-editor__table :deep(.el-input) {
  width: 220px;
}

.rule-editor__candidate-hint {
  max-width: 220px;
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
  line-height: 1.4;
  word-break: break-all;
}

.rule-editor__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
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

.rule-editor__detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.rule-editor__detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
}

.rule-editor__detail-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.rule-editor__detail-value {
  color: var(--color-text-primary);
  font-size: var(--font-size-body);
}

.rule-editor__detail-source {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-editor__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.rule-editor__stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
}

.rule-editor__stat span {
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
}

.rule-editor__stat strong {
  color: var(--color-text-primary);
  font-size: var(--font-size-module-title);
  font-weight: 600;
}

.rule-editor__chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.rule-editor__chip {
  padding: 6px 12px;
  color: var(--color-primary);
  background: var(--color-primary-50);
  border-radius: 999px;
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.rule-editor__template {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  word-break: break-all;
}

.rule-editor__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid #f0f1f3;
}

.rule-editor__version-status {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.rule-editor__action-buttons {
  display: flex;
  gap: 8px;
}

.rule-editor__version-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.rule-editor__version-badge--published {
  background: var(--color-success-bg, #e8f5e9);
  color: var(--color-success, #2e7d32);
}

.rule-editor__version-badge--draft {
  background: var(--color-warning-bg, #fff3e0);
  color: var(--color-warning, #e65100);
}

.rule-editor__version-badge--none {
  color: var(--color-text-tertiary);
}

.rule-editor__version-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-editor__version-info-text {
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
}

.rule-editor__version-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-editor__version-summary-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--color-bg-panel-secondary);
  border-radius: var(--radius-card);
}

.rule-editor__version-summary-name {
  color: var(--color-text-primary);
  font-weight: 500;
  flex: 1;
}

.rule-editor__version-summary-cat {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-editor__version-summary-status {
  font-size: var(--font-size-caption);
  padding: 2px 8px;
  border-radius: 8px;
  background: #f0f1f3;
  color: var(--color-text-tertiary);
}

.rule-editor__version-summary-status.is-active {
  background: var(--color-success-bg, #e8f5e9);
  color: var(--color-success, #2e7d32);
}

@media (max-width: 900px) {
  .rule-editor__form {
    grid-template-columns: 1fr;
  }

  .rule-editor__detail-grid,
  .rule-editor__stats {
    grid-template-columns: 1fr;
  }
}
</style>
