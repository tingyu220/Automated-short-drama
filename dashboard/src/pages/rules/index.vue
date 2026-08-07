<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ElButton, ElMessage } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import RuleEditor, {
  type RuleDraftPayload
} from "@/features/rule-editor/RuleEditor.vue"
import RulePublishPanel from "@/features/rule-publish/RulePublishPanel.vue"
import RuleSimulator from "@/widgets/rule-simulator/RuleSimulator.vue"
import PageHeader from "@/shared/ui/PageHeader.vue"
import { useDeliveryConfigStore } from "@/app/stores/deliveryConfig"
import { useRuleStore } from "@/app/stores/rule"
import type { PriceRuleInput } from "@/widgets/rule-simulator/simulator"

const ruleStore = useRuleStore()
const deliveryConfigStore = useDeliveryConfigStore()

const CATEGORIES = [
  { key: "link", label: "链接规则" },
  { key: "price", label: "价格模板" },
  { key: "material", label: "素材规则" },
  { key: "account", label: "账户数据" },
  { key: "cid", label: "CID预设" },
  { key: "adPreset", label: "广告预设" },
  { key: "openPreset", label: "开户预设" },
  { key: "douyin", label: "抖音号" },
  { key: "platform", label: "平台资源" },
  { key: "naming", label: "任务命名" },
  { key: "runtime", label: "运行参数" },
  { key: "version", label: "版本管理" }
]

const selectedCategory = ref("price")

const priceRules = ref<PriceRuleInput[]>([
  {
    key: "iap_2_9",
    name: "IAP 2.9",
    targetPrice: 2.9,
    minPrice: 2.6,
    maxPrice: 5,
    sameDistanceStrategy: "HIGHER_PRICE_FIRST",
    enabled: true
  },
  {
    key: "iap_9_9",
    name: "IAP 9.9",
    targetPrice: 9.9,
    minPrice: 8.8,
    maxPrice: 13.8,
    sameDistanceStrategy: "HIGHER_PRICE_FIRST",
    enabled: true
  }
])

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
    return priceRuleSets.value[0]?.id ?? null
  }
  return null
})

async function loadVersions() {
  if (selectedRuleSetId.value) {
    await ruleStore.fetchVersions(selectedRuleSetId.value)
  } else {
    ruleStore.clearVersions()
  }
}

async function load() {
  await ruleStore.fetchRules()
  await loadVersions()
  await deliveryConfigStore.loadForCategory(selectedCategory.value)
}

onMounted(load)
watch(selectedCategory, () => {
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
  await Promise.all([ruleStore.fetchRules(), loadVersions()])
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

    <div class="rules-page__layout">
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
          :ad-presets="deliveryConfigStore.adPresets"
          :open-presets="deliveryConfigStore.openPresets"
          :mapping-proposal="deliveryConfigStore.mappingProposal"
          :delivery-loading="deliveryConfigStore.loading"
          v-model:price-rules="priceRules"
          @save-draft="onSaveDraft"
          @publish="(payload) => onPublish(payload.ruleSetId)"
        />
        <RulePublishPanel
          :rule-set-id="selectedRuleSetId"
          :versions="ruleStore.versions"
          :loading="ruleStore.loading"
          :error="ruleStore.error"
          :busy="ruleStore.loading"
          @validate="onValidate"
          @publish="onPublish"
          @retry="loadVersions"
        />
      </div>

      <aside class="rules-page__side">
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
  grid-template-columns: 200px minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
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
