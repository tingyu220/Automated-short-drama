<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ElButton, ElMessage, ElOption, ElSelect } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import RuleEditor, {
  type MappingRow,
  type RuleDraftPayload
} from "@/features/rule-editor/RuleEditor.vue"
import RulePublishPanel from "@/features/rule-publish/RulePublishPanel.vue"
import RuleSimulator from "@/widgets/rule-simulator/RuleSimulator.vue"
import PageHeader from "@/shared/ui/PageHeader.vue"
import { useDeliveryConfigStore } from "@/app/stores/deliveryConfig"
import { useSessionStore } from "@/app/stores/session"
import { useRuleStore } from "@/app/stores/rule"
import type { PriceRuleInput } from "@/widgets/rule-simulator/simulator"
import { rulesLayoutClass } from "./layout"

const ruleStore = useRuleStore()
const deliveryConfigStore = useDeliveryConfigStore()
const sessionStore = useSessionStore()

const mappingProposal = computed(
  () => deliveryConfigStore.mappingProposal as unknown as MappingRow[]
)

const platformResources = computed(() => {
  const sessions = sessionStore.sessions
  const platforms: { key: string; label: string }[] = [
    { key: "feishu", label: "飞书" },
    { key: "tomato", label: "番茄" },
    { key: "delivery", label: "投放系统" },
    { key: "ocean", label: "巨量" }
  ]
  return platforms.map((item) => {
    const session = sessions[item.key]
    return {
      platform: item.label,
      status: session?.status === "logged_in" ? "已登录" : "未登录",
      url: session?.login_url ?? "—"
    }
  })
})

const CATEGORIES = [
  { key: "price", label: "价格模板" },
  { key: "material", label: "素材规则" },
  { key: "cid", label: "CID预设" },
  { key: "adPreset", label: "广告预设" },
  { key: "openPreset", label: "开户预设" },
  { key: "platform", label: "平台资源" },
  { key: "runtime", label: "运行参数" },
  { key: "version", label: "版本管理" }
]

const selectedCategory = ref("price")
const selectedVersionRuleSetId = ref("")

const priceRules = ref<PriceRuleInput[]>([])

const PRICE_RULE_NAMES: Record<string, string> = {
  iap_2_9: "IAP 2.9",
  iap_9_9: "IAP 9.9"
}

function syncPriceRulesFromStore() {
  priceRules.value = ruleStore.priceRules.map((rule) => ({
    key: rule.key,
    name: PRICE_RULE_NAMES[rule.key] ?? rule.key,
    targetPrice: rule.target_price,
    minPrice: rule.min_price,
    maxPrice: rule.max_price,
    sameDistanceStrategy: rule.same_distance_strategy,
    enabled: rule.enabled
  }))
}

const materialRuleRows = computed(() => ruleStore.materialRules)

const priceRuleSets = computed(() =>
  ruleStore.ruleSets.filter((rule) => rule.category === "价格模板")
)
const materialRuleSets = computed(() =>
  ruleStore.ruleSets.filter((rule) => rule.category === "素材规则")
)

const selectedRuleSetId = computed(() => {
  if (selectedCategory.value === "price") {
    return priceRuleSets.value[0]?.id ?? null
  }
  if (selectedCategory.value === "material") {
    return materialRuleSets.value[0]?.id ?? null
  }
  if (selectedCategory.value === "version") {
    return selectedVersionRuleSetId.value || null
  }
  return null
})

const selectedVersionRuleSet = computed(() =>
  ruleStore.ruleSets.find((ruleSet) => ruleSet.id === selectedRuleSetId.value) ?? null
)

async function loadVersions() {
  if (selectedRuleSetId.value) {
    await ruleStore.fetchVersions(selectedRuleSetId.value)
  } else {
    ruleStore.clearVersions()
  }
}

async function load() {
  await Promise.all([
    ruleStore.fetchRules(),
    ruleStore.fetchPriceRules(),
    ruleStore.fetchMaterialRules(),
    sessionStore.fetchSessions()
  ])
  syncPriceRulesFromStore()
  await loadVersions()
  await deliveryConfigStore.loadForCategory("cid")
  await deliveryConfigStore.loadForCategory(selectedCategory.value)
}

onMounted(load)
watch(selectedCategory, () => {
  if (selectedCategory.value === "version" && !selectedVersionRuleSetId.value) {
    selectedVersionRuleSetId.value = ruleStore.ruleSets[0]?.id ?? ""
  }
  void loadVersions()
  void deliveryConfigStore.loadForCategory(selectedCategory.value)
})

async function onSaveDraft(payload: RuleDraftPayload) {
  if (!payload.ruleSetId) {
    ElMessage.warning("当前分类没有可选规则集")
    return
  }
  const version = await ruleStore.saveDraft(payload.ruleSetId, payload.data)
  if (ruleStore.error || !version) {
    ElMessage.error(ruleStore.error ?? "保存草稿失败")
    return
  }
  ElMessage.success(`「${payload.category}」草稿已保存，版本 v${version.version}`)
  await loadVersions()
}

async function onValidate(ruleSetId: string) {
  const version = await ruleStore.validate(ruleSetId)
  if (ruleStore.error) {
    ElMessage.error(ruleStore.error)
    return
  }
  if (version) {
    ElMessage.success(`校验通过，版本 v${version.version} 已生成`)
  }
  await loadVersions()
}

async function onPublish(ruleSetId: string) {
  const hasPending = ruleStore.versions.some(
    (version) => version.status === "DRAFT" || version.status === "VALIDATING"
  )
  if (!hasPending) {
    const validated = await ruleStore.validate(ruleSetId)
    if (ruleStore.error || !validated) {
      ElMessage.error(ruleStore.error ?? "校验失败")
      return
    }
  }
  const version = await ruleStore.publish(ruleSetId)
  if (ruleStore.error || !version) {
    ElMessage.error(ruleStore.error ?? "发布失败")
    return
  }
  ElMessage.success(`已发布版本 v${version.version}`)
  await Promise.all([
    ruleStore.fetchRules(),
    ruleStore.fetchPriceRules(),
    ruleStore.fetchMaterialRules(),
    loadVersions()
  ])
  syncPriceRulesFromStore()
}

async function onSaveMapping(rows: MappingRow[]) {
  const result = await deliveryConfigStore.saveMappingProposal(rows)
  if (deliveryConfigStore.error || !result) {
    ElMessage.error(deliveryConfigStore.error ?? "保存映射失败")
    return
  }
  ElMessage.success(`CID 映射已保存，共 ${result.count} 条`)
}

async function onSaveSettings(
  values: Record<string, Record<string, unknown>>
) {
  const result = await deliveryConfigStore.saveSettings(values)
  if (deliveryConfigStore.error || !result) {
    ElMessage.error(deliveryConfigStore.error ?? "保存配置失败")
    return
  }
  ElMessage.success(`「${selectedCategory.value}」配置已保存`)
}
</script>

<template>
  <div class="rules-page">
    <PageHeader
      title="规则与配置"
      subtitle="规则草稿、校验、发布与实时模拟"
    >
      <template #actions>
        <ElButton :loading="ruleStore.loading" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </ElButton>
      </template>
    </PageHeader>

    <div
      class="rules-page__layout"
      :class="rulesLayoutClass(selectedCategory)"
    >
      <aside class="rules-nav" aria-label="规则分类">
        <button
          v-for="category in CATEGORIES"
          :key="category.key"
          type="button"
          class="rules-nav__item"
          :class="{ 'is-active': selectedCategory === category.key }"
          @click="selectedCategory = category.key"
        >
          {{ category.label }}
        </button>
      </aside>

      <div class="rules-page__main">
        <RuleEditor
          :category="selectedCategory"
          :rule-sets="ruleStore.ruleSets"
          :busy="ruleStore.loading"
          :cids="deliveryConfigStore.cids"
          :accounts="deliveryConfigStore.accounts"
          :ad-presets="deliveryConfigStore.adPresets"
          :open-presets="deliveryConfigStore.openPresets"
          :material-rules="materialRuleRows"
          :mapping-proposal="mappingProposal"
          :delivery-loading="deliveryConfigStore.loading"
          :saving="deliveryConfigStore.saving"
          :platform-resources="platformResources"
          :settings="deliveryConfigStore.settings"
          :settings-options="deliveryConfigStore.settingsOptions"
          :settings-saving="deliveryConfigStore.settingsSaving"
          :versions="ruleStore.versions"
          v-model:price-rules="priceRules"
          @save-draft="onSaveDraft"
          @publish="(payload) => onPublish(payload.ruleSetId)"
          @save-mapping="onSaveMapping"
          @save-settings="onSaveSettings"
        />
        <section v-if="selectedCategory === 'version'" class="rules-page__version-picker">
          <span class="rules-page__version-picker-label">选择规则集</span>
          <ElSelect
            v-model="selectedVersionRuleSetId"
            placeholder="请选择规则集"
            @change="loadVersions"
          >
            <ElOption
              v-for="ruleSet in ruleStore.ruleSets"
              :key="ruleSet.id"
              :label="ruleSet.name + '（' + ruleSet.category + '）'"
              :value="ruleSet.id"
            />
          </ElSelect>
        </section>
        <RulePublishPanel
          v-if="selectedCategory === 'version'"
          :rule-set-id="selectedRuleSetId"
          :rule-set-name="selectedVersionRuleSet?.name"
          :versions="ruleStore.versions"
          :loading="ruleStore.loading"
          :error="ruleStore.error"
          :busy="ruleStore.loading"
          @validate="onValidate"
          @publish="onPublish"
          @retry="loadVersions"
        />
      </div>

      <aside v-if="selectedCategory === 'price'" class="rules-page__side">
        <RuleSimulator :rules="priceRules" />
      </aside>
    </div>
  </div>
</template>

<style scoped>
.rules-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rules-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.rules-page__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-page-title);
  font-weight: 600;
}

.rules-page__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-body);
}

.rules-page__layout {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.rules-page__layout--with-side {
  grid-template-columns: 200px minmax(0, 1fr) 340px;
}

.rules-page__layout--full .rules-page__main {
  width: 100%;
}

.rules-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.rules-nav__item {
  height: 34px;
  padding: 0 12px;
  border: none;
  border-radius: var(--radius-button);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.rules-nav__item:hover {
  background: var(--color-bg-panel-secondary);
  color: var(--color-text-primary);
}

.rules-nav__item.is-active {
  background: var(--color-primary-50);
  color: var(--color-primary);
  font-weight: 600;
}

.rules-page__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.rules-page__side {
  min-width: 0;
}

.rules-page__version-picker {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
  color: var(--color-text-secondary);
  font-size: var(--font-size-body);
}

.rules-page__version-picker-label {
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
}

.rules-page__version-picker :deep(.el-select) {
  width: 260px;
}

@media (max-width: 1360px) {
  .rules-page__layout {
    grid-template-columns: 180px minmax(0, 1fr);
  }

  .rules-page__side {
    grid-column: 1 / -1;
  }
}

@media (max-width: 960px) {
  .rules-page__layout {
    grid-template-columns: 1fr;
  }

  .rules-nav {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
