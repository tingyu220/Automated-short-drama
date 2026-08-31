# 规则配置编辑器改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让规则配置页面以单一数据来源编辑规则，支持预设候选与手动输入、表格分页和清晰的版本说明。

**Architecture:** 保持 API 与 Store 边界不变；新增独立的前端分页工具，并由 RuleEditor 统一渲染配置编辑与本地分页。右侧模拟器由规则页按分类条件渲染，只消费价格模板草稿。

**Tech Stack:** Vue 3、TypeScript、Pinia、Element Plus、Vitest。

---

### Task 1: 规则页显示边界

**Files:**
- Modify: `dashboard/src/pages/rules/index.vue`
- Test: `dashboard/tests/unit/rules-page.spec.ts`

- [ ] **Step 1: Write the failing test**

```ts
expect(wrapper.find('[aria-label="规则模拟"]').exists()).toBe(false)
await wrapper.get('button').trigger('click')
expect(wrapper.find('[aria-label="规则模拟"]').exists()).toBe(true)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- rules-page.spec.ts`
Expected: FAIL because the simulator is always rendered.

- [ ] **Step 3: Write minimal implementation**

```vue
<aside v-if="selectedCategory === 'price'" class="rules-page__side">
  <RuleSimulator :rules="priceRules" />
</aside>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- rules-page.spec.ts`
Expected: PASS.

### Task 2: 可编辑预设与分页表格

**Files:**
- Create: `dashboard/src/features/rule-editor/pagination.ts`
- Modify: `dashboard/src/features/rule-editor/RuleEditor.vue`
- Test: `dashboard/tests/unit/rule-editor.spec.ts`

- [ ] **Step 1: Write the failing tests**

```ts
expect(wrapper.findAll('tbody tr')).toHaveLength(10)
expect(wrapper.text()).toContain('共 12 条')
expect(wrapper.find('input').exists()).toBe(true)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- rule-editor.spec.ts`
Expected: FAIL because all rows render and preset rows are read-only.

- [ ] **Step 3: Write minimal implementation**

```ts
export function paginateRows<T>(rows: T[], page: number, pageSize: number): T[] {
  return rows.slice((page - 1) * pageSize, page * pageSize)
}
```

Use `ElSelect` with `filterable`, `allow-create`, and editable inputs in CID mapping; render preset tables through the shared paginated rows.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- rule-editor.spec.ts`
Expected: PASS.

### Task 3: 单一规则来源与任务命名

**Files:**
- Modify: `dashboard/src/features/rule-editor/RuleEditor.vue`
- Test: `dashboard/tests/unit/rule-editor.spec.ts`

- [ ] **Step 1: Write failing tests**

```ts
expect(wrapper.text()).not.toContain('IAP 2.9 模板')
expect(wrapper.text()).toContain('<平台方>#端免<剧名称><日期>bxr-')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- rule-editor.spec.ts`
Expected: FAIL because link settings duplicate pricing and naming options depend on crawled ad presets.

- [ ] **Step 3: Write minimal implementation**

Remove price fields from link settings and supply the three documented naming templates as the authoritative options.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- rule-editor.spec.ts`
Expected: PASS.

### Task 4: Full verification

**Files:**
- Verify: `dashboard/tests/unit/*.spec.ts`
- Verify: `dashboard/src/**/*.vue`

- [ ] **Step 1: Run unit tests**

Run: `npm test`
Expected: PASS.

- [ ] **Step 2: Run production build**

Run: `npm run build`
Expected: exit code 0.

- [ ] **Step 3: Review changed files**

Run: `git status --short dashboard docs/superpowers/plans/2026-08-08-rule-config-editor-improvement.md`
Expected: only intended Dashboard files and this plan.
