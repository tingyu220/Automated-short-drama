# 链接准备阶段 Dashboard UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在任务列表、任务详情和当前运行任务区域清晰展示当前已启用的链接准备阶段，并支持用户指定运行终点。

**Architecture:** 新增纯展示组件 `LinkReadinessTimeline`，将固定的五阶段状态计算集中在任务领域类型辅助函数中。任务详情复用现有 API 字段 `current_stage`、`target_stage`、`steps` 与产物字段；首页当前任务和任务列表只消费同一阶段模型，不修改后端接口。

**Tech Stack:** Vue 3、TypeScript、Element Plus、Vitest、现有 CSS 变量。

## Global Constraints

- 当前只展示并执行到 `LINK_READY`，不展示账户、素材、计划、提交和状态确认阶段。
- 阶段顺序固定为 `WAITING_AVAILABLE_TIME → LINK_EXTRACTION → DELIVERY_DRAMA → PROMOTION_CONFIG → LINK_READY`。
- 保留现有“仅提取链接”和“搭建链接完成”两个运行终点。
- 不新增依赖，不修改后端阶段接口，不提交 Git。
- UI 必须支持窄屏、键盘焦点和失败/空数据状态。

---

### Task 1: 阶段模型与失败测试

**Files:**
- Modify: `dashboard/src/entities/task/types.ts`
- Create: `dashboard/tests/unit/link-readiness-timeline.spec.ts`
- Modify: `dashboard/tests/unit/task-detail.spec.ts`

**Interfaces:**
- Produces: `LINK_READINESS_STAGES`、`buildLinkReadinessStages(currentStage, taskStatus, steps)`。
- `LinkReadinessStageNode` 包含 `key`、`label`、`status`、`detail`。

- [ ] **Step 1: Write the failing test**

```ts
it("按当前阶段生成已完成、进行中和待处理状态", () => {
  const stages = buildLinkReadinessStages("DELIVERY_DRAMA", "RUNNING", [])
  expect(stages.map((stage) => stage.status)).toEqual([
    "done", "done", "current", "pending", "pending"
  ])
})

it("链接已就绪时五个阶段全部完成", () => {
  const stages = buildLinkReadinessStages("LINK_READY", "LINK_READY", [])
  expect(stages.every((stage) => stage.status === "done")).toBe(true)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run dashboard/tests/unit/link-readiness-timeline.spec.ts`
Expected: FAIL because the stage model and builder do not exist.

- [ ] **Step 3: Write minimal implementation**

Add the five-stage constant and a pure status builder. Treat `LINK_EXTRACTED` as completion of `LINK_EXTRACTION`, `MANUAL_REVIEW`/`FAILED` as failure of the current recorded step, and keep unknown states pending.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run dashboard/tests/unit/link-readiness-timeline.spec.ts dashboard/tests/unit/task-detail.spec.ts`
Expected: PASS.

### Task 2: 链接准备阶段组件与详情接入

**Files:**
- Create: `dashboard/src/widgets/link-readiness-timeline/LinkReadinessTimeline.vue`
- Modify: `dashboard/src/features/task-detail/TaskDetailDrawer.vue`
- Modify: `dashboard/tests/unit/task-detail.spec.ts`

**Interfaces:**
- Consumes: `LinkReadinessStageNode[]` and `TaskView` stage fields.
- Produces: accessible horizontal/vertical responsive timeline with current/failure markers.

- [ ] **Step 1: Write the failing test**

```ts
it("详情显示完整的链接准备阶段轨道", () => {
  const wrapper = mount(TaskDetailDrawer, { props: { open: true, task } })
  expect(wrapper.get('[aria-label="链接准备阶段进度"]').text()).toContain("搭建投放剧目")
  expect(wrapper.text()).toContain("当前阶段")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run dashboard/tests/unit/task-detail.spec.ts`
Expected: FAIL because the drawer has no fixed stage progress component.

- [ ] **Step 3: Write minimal implementation**

Render a semantic `ol` with `aria-current="step"` for the current node, status text for every node, and compact detail text. Keep the existing run target select/button beside the timeline. On screens below 720px, switch nodes to a vertical list without horizontal clipping.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run dashboard/tests/unit/task-detail.spec.ts dashboard/tests/unit/link-readiness-timeline.spec.ts`
Expected: PASS.

### Task 3: 任务列表与当前运行任务统一阶段语义

**Files:**
- Modify: `dashboard/src/pages/tasks/index.vue`
- Modify: `dashboard/src/widgets/current-task/CurrentTaskPanel.vue`
- Modify: `dashboard/src/widgets/task-table/TaskTable.vue`
- Modify: `dashboard/tests/unit/task-stage-control.spec.ts`

**Interfaces:**
- Consumes: `buildLinkReadinessStages` and `TaskView.current_stage`.
- Produces: visible current-stage column/badge and current-task link-readiness timeline; existing queue actions remain unchanged.

- [ ] **Step 1: Write the failing test**

```ts
it("任务列表显示链接准备当前阶段", () => {
  expect(wrapper.text()).toContain("提取番茄链接")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run dashboard/tests/unit/task-stage-control.spec.ts`
Expected: FAIL because the table/current-task panel still uses the old full-workflow track.

- [ ] **Step 3: Write minimal implementation**

Replace the homepage full-workflow nodes with the five link-readiness nodes. Add a compact “当前阶段” field to the task table that falls back to task status when no stage is available. Do not expose future stages.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run dashboard/tests/unit/task-stage-control.spec.ts dashboard/tests/unit/task-detail.spec.ts`
Expected: PASS.

### Task 4: Full verification

- [ ] **Step 1: Run frontend unit tests**

Run: `npm test -- --run`
Expected: all existing and new tests pass.

- [ ] **Step 2: Build the dashboard**

Run: `npm run build`
Expected: production build succeeds; existing chunk-size warning may remain.

- [ ] **Step 3: Check formatting and visual states**

Run: `git diff --check`; review the task detail at desktop and narrow viewport with `LINK_EXTRACTION`, `DELIVERY_DRAMA`, `LINK_READY`, and failed states.
