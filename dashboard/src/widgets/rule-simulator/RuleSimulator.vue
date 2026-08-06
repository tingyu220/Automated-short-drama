<script setup lang="ts">
import { computed, ref } from "vue"
import { ElInput } from "element-plus"
import EmptyState from "@/shared/ui/EmptyState.vue"
import StatusDot from "@/shared/ui/StatusDot.vue"
import {
  parseCandidates,
  simulatePriceCandidates,
  type PriceRuleInput,
  type PriceSimulationRow
} from "./simulator"

const props = withDefaults(defineProps<{ rules?: PriceRuleInput[] }>(), {
  rules: () => []
})

const candidatesText = ref("2.8, 3.0, 4.9")

const candidates = computed(() => parseCandidates(candidatesText.value))
const rows = computed<PriceSimulationRow[]>(() =>
  simulatePriceCandidates(candidates.value, props.rules)
)
const enabledCount = computed(
  () => props.rules.filter((rule) => rule.enabled).length
)
</script>

<template>
  <section class="rule-simulator" aria-label="规则模拟">
    <header class="rule-simulator__header">
      <div>
        <h2 class="rule-simulator__title">规则模拟</h2>
        <p class="rule-simulator__subtitle">按当前启用价格模板实时计算</p>
      </div>
      <span class="rule-simulator__count">启用 {{ enabledCount }} 条</span>
    </header>

    <label class="rule-simulator__label" for="rule-simulator-candidates">
      候选价格
    </label>
    <ElInput
      id="rule-simulator-candidates"
      v-model="candidatesText"
      placeholder="用逗号分隔，例如 2.8, 3.0, 4.9"
      clearable
    />

    <EmptyState
      v-if="rules.length === 0"
      title="暂无价格规则"
      description="在价格模板中配置后即可模拟"
    />
    <template v-else>
      <p v-if="candidates.length === 0" class="rule-simulator__hint">
        请输入至少一个数字价格
      </p>
      <div v-else class="rule-simulator__scroll">
        <table class="rule-simulator__table">
          <thead>
            <tr>
              <th>候选价格</th>
              <th>是否匹配</th>
              <th>距离目标价</th>
              <th>最终选择</th>
              <th>选择理由</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.candidate">
              <td class="rule-simulator__mono">{{ row.candidate }}</td>
              <td>
                <span class="rule-simulator__status">
                  <StatusDot
                    :color="
                      row.matched
                        ? 'var(--color-status-success)'
                        : 'var(--color-status-failed)'
                    "
                  />
                  {{ row.matched ? "匹配" : "区间外" }}
                </span>
              </td>
              <td>{{ row.distance?.toFixed(2) ?? "—" }}</td>
              <td>{{ row.ruleName ?? "—" }}</td>
              <td class="rule-simulator__reason">
                {{ row.matched ? row.selectionReason : "不在任何启用区间内" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.rule-simulator {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: var(--color-bg-panel);
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-panel);
}

.rule-simulator__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.rule-simulator__title {
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.rule-simulator__subtitle {
  margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-simulator__count {
  flex: none;
  padding: 2px 8px;
  color: var(--color-primary);
  background: var(--color-primary-50);
  border-radius: 999px;
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.rule-simulator__label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.rule-simulator__hint {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-caption);
}

.rule-simulator__scroll {
  overflow-x: auto;
}

.rule-simulator__table {
  width: 100%;
  min-width: 520px;
  border-collapse: collapse;
  font-size: var(--font-size-table);
}

.rule-simulator__table th {
  padding: 8px 10px;
  color: var(--color-text-secondary);
  background: var(--color-bg-panel-secondary);
  font-size: var(--font-size-caption);
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #eef0f3;
}

.rule-simulator__table td {
  padding: 8px 10px;
  color: var(--color-text-primary);
  white-space: nowrap;
  border-bottom: 1px solid #f0f1f3;
}

.rule-simulator__table tbody tr:last-child td {
  border-bottom: none;
}

.rule-simulator__mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.rule-simulator__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.rule-simulator__reason {
  color: var(--color-text-secondary);
}
</style>
