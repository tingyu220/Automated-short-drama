<script setup lang="ts">
import type { LinkReadinessStageNode } from "@/entities/task/types"

withDefaults(
  defineProps<{
    stages: LinkReadinessStageNode[]
    compact?: boolean
  }>(),
  { compact: false }
)

function statusLabel(status: LinkReadinessStageNode["status"]): string {
  return {
    done: "已完成",
    current: "进行中",
    pending: "待执行",
    failed: "需处理"
  }[status]
}
</script>

<template>
  <section
    class="link-readiness"
    :class="{ 'is-compact': compact }"
    aria-label="链接准备阶段进度"
  >
    <div class="link-readiness__heading">
      <div>
        <h3>链接准备进度</h3>
      </div>
      <span class="link-readiness__scope">当前自动化范围</span>
    </div>
    <ol class="link-readiness__list">
      <li
        v-for="(stage, index) in stages"
        :key="stage.key"
        class="link-readiness__item"
        :class="`is-${stage.status}`"
        :aria-current="stage.status === 'current' ? 'step' : undefined"
      >
        <div class="link-readiness__marker-wrap">
          <span class="link-readiness__marker" aria-hidden="true">
            <span v-if="stage.status === 'done'">✓</span>
            <span v-else-if="stage.status === 'failed'">!</span>
            <span v-else>{{ index + 1 }}</span>
          </span>
          <span v-if="index < stages.length - 1" class="link-readiness__connector" aria-hidden="true" />
        </div>
        <div class="link-readiness__content">
          <div class="link-readiness__title-row">
            <strong>{{ stage.label }}</strong>
            <span class="link-readiness__status">{{ statusLabel(stage.status) }}</span>
          </div>
          <p>{{ stage.detail }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.link-readiness {
  padding: 16px;
  margin: 0 4px 18px;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-card);
  background: var(--color-bg-panel);
}

.link-readiness__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.link-readiness.is-compact {
  padding: 0;
  margin: 0;
  border: 0;
  background: transparent;
}

.link-readiness h3 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--font-size-card-title);
  font-weight: 600;
}

.link-readiness__scope {
  flex: none;
  padding: 4px 8px;
  border: 1px solid #dbe2f0;
  border-radius: 999px;
  color: var(--color-primary);
  background: #f7f9ff;
  font-size: 11px;
  white-space: nowrap;
}

.link-readiness__list {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  list-style: none;
  margin: 0;
  padding: 0;
}

.link-readiness__item {
  position: relative;
  min-width: 0;
  padding-right: 12px;
}

.link-readiness__marker-wrap {
  position: relative;
  display: flex;
  align-items: center;
  height: 26px;
}

.link-readiness__marker {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 2px solid #cbd5e1;
  border-radius: 50%;
  color: var(--color-text-tertiary);
  background: var(--color-bg-panel);
  font-size: 11px;
  font-weight: 700;
}

.link-readiness__connector {
  position: absolute;
  top: 12px;
  left: 24px;
  right: 0;
  height: 2px;
  background: #e5e7eb;
}

.link-readiness__content {
  padding-top: 8px;
  padding-right: 4px;
}

.link-readiness__title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.link-readiness__title-row strong {
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-caption);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-readiness__status {
  flex: none;
  color: var(--color-text-tertiary);
  font-size: 11px;
}

.link-readiness__content p {
  overflow: hidden;
  margin: 4px 0 0;
  color: var(--color-text-tertiary);
  font-size: 11px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-readiness__item.is-done .link-readiness__marker {
  border-color: var(--color-status-success);
  color: var(--color-status-success);
}

.link-readiness__item.is-done .link-readiness__connector {
  background: var(--color-status-success);
}

.link-readiness__item.is-current .link-readiness__marker {
  border-color: var(--color-status-running);
  color: var(--color-status-running);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-status-running) 14%, transparent);
}

.link-readiness__item.is-current .link-readiness__title-row strong,
.link-readiness__item.is-current .link-readiness__status {
  color: var(--color-status-running);
}

.link-readiness__item.is-failed .link-readiness__marker,
.link-readiness__item.is-failed .link-readiness__title-row strong,
.link-readiness__item.is-failed .link-readiness__status {
  border-color: var(--color-status-failed);
  color: var(--color-status-failed);
}

@media (prefers-reduced-motion: no-preference) {
  .link-readiness__item.is-current .link-readiness__marker {
    animation: link-readiness-pulse 1.8s ease-in-out infinite;
  }
}

@keyframes link-readiness-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-status-running) 12%, transparent);
  }
  50% {
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--color-status-running) 4%, transparent);
  }
}

@media (max-width: 720px) {
  .link-readiness__heading {
    flex-direction: column;
  }

  .link-readiness__list {
    display: flex;
    flex-direction: column;
  }

  .link-readiness__item {
    display: flex;
    gap: 10px;
    min-height: 58px;
    padding: 0;
  }

  .link-readiness__marker-wrap {
    width: 24px;
    height: auto;
    flex: none;
    align-items: flex-start;
  }

  .link-readiness__connector {
    top: 24px;
    bottom: -18px;
    left: 11px;
    right: auto;
    width: 2px;
    height: auto;
  }

  .link-readiness__content {
    flex: 1;
    padding: 0 0 12px;
  }

  .link-readiness__title-row {
    justify-content: flex-start;
  }

  .link-readiness__content p {
    white-space: normal;
  }
}
</style>
