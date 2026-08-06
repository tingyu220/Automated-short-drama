<script setup lang="ts">
import { computed } from "vue"
import {
  getWorkflowNodeMeta,
  WORKFLOW_STEPS,
  type WorkflowStepNode
} from "@/entities/task/types"

const props = withDefaults(defineProps<{ steps?: WorkflowStepNode[] }>(), {
  steps: () => WORKFLOW_STEPS
})

const nodes = computed(() =>
  props.steps && props.steps.length > 0 ? props.steps : WORKFLOW_STEPS
)
</script>

<template>
  <ol class="workflow-timeline" aria-label="工作流轨道">
    <li
      v-for="(step, index) in nodes"
      :key="step.key"
      class="workflow-timeline__node"
      :class="[`is-${step.status}`, { 'is-last': index === nodes.length - 1 }]"
      :aria-current="step.status === 'current' ? 'step' : undefined"
    >
      <span
        class="workflow-timeline__dot"
        :style="{ backgroundColor: getWorkflowNodeMeta(step.status).color }"
        aria-hidden="true"
      />
      <span class="workflow-timeline__label">{{ step.label }}</span>
      <span class="workflow-timeline__status">
        {{ getWorkflowNodeMeta(step.status).label }}
      </span>
    </li>
  </ol>
</template>

<style scoped>
.workflow-timeline {
  display: flex;
  align-items: flex-start;
  gap: 0;
  list-style: none;
  overflow-x: auto;
  padding: 4px 0;
}

.workflow-timeline__node {
  position: relative;
  display: flex;
  flex: 1 1 0;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 64px;
}

.workflow-timeline__node:not(.is-last)::after {
  position: absolute;
  top: 8px;
  left: calc(50% + 13px);
  width: calc(100% - 26px);
  height: 2px;
  background: var(--color-bg-panel-secondary);
  border-radius: 1px;
  content: "";
}

.workflow-timeline__node.is-done:not(.is-last)::after {
  background: var(--color-status-success);
}

.workflow-timeline__dot {
  position: relative;
  z-index: 1;
  display: block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--color-bg-panel);
  border-radius: 50%;
  box-shadow: 0 0 0 1px var(--color-bg-panel-secondary);
}

.workflow-timeline__node.is-current .workflow-timeline__dot {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-status-running) 25%, transparent);
  animation: workflow-timeline-pulse 1.6s ease-in-out infinite;
}

.workflow-timeline__node.is-pending .workflow-timeline__dot {
  opacity: 0.55;
}

.workflow-timeline__node.is-skipped .workflow-timeline__dot {
  border-style: dashed;
  opacity: 0.5;
}

.workflow-timeline__label {
  color: var(--color-text-primary);
  font-size: var(--font-size-caption);
  font-weight: 500;
  white-space: nowrap;
}

.workflow-timeline__node.is-current .workflow-timeline__label {
  color: var(--color-status-running);
}

.workflow-timeline__node.is-failed .workflow-timeline__label {
  color: var(--color-status-failed);
}

.workflow-timeline__status {
  color: var(--color-text-tertiary);
  font-size: 11px;
  white-space: nowrap;
}

@keyframes workflow-timeline-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}
</style>
