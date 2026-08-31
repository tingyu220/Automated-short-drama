<script setup lang="ts">
import { computed } from "vue"
import {
  CircleCheck,
  Clock,
  Finished,
  Switch,
  VideoPlay,
  Warning
} from "@element-plus/icons-vue"
import MetricCard from "@/shared/ui/MetricCard.vue"
import type { QueueItemView, TaskBase } from "@/entities/task/types"

const props = defineProps<{
  tasks: TaskBase[]
  queueItems: QueueItemView[]
  loading?: boolean
}>()

const stats = computed(() => {
  const activeQueueTaskIds = new Set(
    props.queueItems
      .filter(
        (item) => item.state !== "COMPLETED" && item.state !== "CANCELLED"
      )
      .map((item) => item.task_id)
  )
  const tasksWithoutActiveQueue = props.tasks.filter(
    (task) => !activeQueueTaskIds.has(task.id)
  )
  const queueCount = (state: string) =>
    props.queueItems.filter((item) => item.state === state).length
  const taskCount = (status: string) =>
    tasksWithoutActiveQueue.filter((task) => task.status === status).length
  return {
    waiting: queueCount("WAITING_TIME") + taskCount("WAITING_TIME"),
    queued: queueCount("QUEUED"),
    running: queueCount("RUNNING") + queueCount("CLAIMED") + taskCount("RUNNING"),
    manual: queueCount("MANUAL_REVIEW") + taskCount("MANUAL_REVIEW"),
    ready: taskCount("READY"),
    completed: taskCount("COMPLETED")
  }
})

const cards = computed(() => [
  {
    key: "waiting",
    title: "等待时间",
    desc: "到达可执行时间前",
    to: "/queue",
    icon: Clock
  },
  {
    key: "queued",
    title: "排队中",
    desc: "等待 Worker 认领",
    to: "/queue",
    icon: Switch
  },
  {
    key: "running",
    title: "运行中",
    desc: "当前执行任务",
    to: "/",
    icon: VideoPlay
  },
  {
    key: "manual",
    title: "人工处理",
    desc: "需要人工介入",
    to: "/exceptions",
    icon: Warning
  },
  {
    key: "ready",
    title: "准备完成",
    desc: "可手动入队",
    to: "/tasks",
    icon: CircleCheck
  },
  {
    key: "completed",
    title: "计划已完成",
    desc: "今日交付计划",
    to: "/plans",
    icon: Finished
  }
])

const displayValue = (key: string): string | number => {
  if (props.loading && props.tasks.length === 0) return "—"
  return stats.value[key as keyof typeof stats.value]
}
</script>

<template>
  <section class="task-overview" aria-label="任务概览">
    <MetricCard
      v-for="card in cards"
      :key="card.key"
      :title="card.title"
      :value="displayValue(card.key)"
      :desc="card.desc"
      :to="card.to"
      :icon="card.icon"
    />
  </section>
</template>

<style scoped>
.task-overview {
  display: grid;
  grid-template-columns: repeat(6, minmax(140px, 1fr));
  gap: 16px;
}

@media (max-width: 1180px) {
  .task-overview {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .task-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
