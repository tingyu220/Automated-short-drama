# 前端展示逻辑甲方审查报告

> 审查日期：2026-08-07
> 审查方式：codegraph 索引（276 文件 / 4202 节点 / 10744 边）+ 前后端契约逐项核对 + 本地数据库抽样
> 审查视角：甲方（业务方）验收视角，只关注“页面显示是否可信、操作是否可用”，不评价代码风格

## 1. 总体结论

页面骨架、视觉层级和基础状态组件已经成型，但当前版本**展示层大量数据来自前端写死的默认值或空占位**，多个页面看起来“有功能”，实际拿不到真实数据，部分统计口径还会误导业务判断。按甲方验收标准，当前不能视为可交付版本。

按严重度分类：

- P0 数据错误/误导决策：5 项
- P1 功能不可用/占位冒充真实功能：7 项
- P2 体验与一致性：6 项

## 2. P0 问题

### P0-1 全部时间显示偏差 8 小时

后端所有时间按 UTC 落库（`available_time` 实际值 `2026-08-07 10:00:00` 表示本地 18:00），API 序列化为不带时区的 naive ISO 字符串；前端 `formatDateTime` / `Date.parse` 按本地时间解析，导致投放时间、更新时间、事件时间整体显示早 8 小时。

同时“今日任务”日期筛选在 `backend/interfaces/api/routes/tasks.py` 用 UTC 零点做日界，而页面用本地日期，东八区凌晨 00:00-08:00 投放的任务会被判到“前一天”，前端日期筛选也漏任务。

证据：
- 数据库 `drama_task.available_time = 2026-08-07 10:00:00`，实际本地业务时间是 18:00
- `dashboard/src/entities/task/types.ts`、`dashboard/src/shared/utils/format.ts` 的 `formatDateTime`
- `backend/src/backend/interfaces/api/routes/tasks.py` 的 UTC `datetime.combine`
- `backend/src/backend/platforms/feishu/sheet_parser.py` 已按东八区转 UTC，但展示层没有再转回

修复方向：API 统一返回带 `Z` 的 UTC 时间，前端统一转东八区展示；任务日期筛选改按东八区日界。

### P0-2 今日任务表大量列永远为空

任务列表接口只返回 `TaskSummary` 基础字段，但表格和详情抽屉展示：当前阶段、IAA、9.9、2.9、专辑ID、产品库、PlanSpec、计划状态。这些字段接口从不返回，页面长期显示“—/未生成”，但页面标题和表头仍按真实数据设计。

证据：
- `backend/src/backend/interfaces/api/schemas.py` 的 `TaskSummary` / `TaskDetail` 字段集合
- `dashboard/src/widgets/task-table/TaskTable.vue` 列定义
- `dashboard/src/features/task-detail/TaskDetailDrawer.vue` 概览字段

修复方向：要么后端详情/列表补齐字段，要么前端删除空列并改为“详情页查看”，二选一，不能留“永远为空”的列。

### P0-3 计划管理页整页是空数据

`/records/ledgers` 返回的 `LedgerView` 只有台账基础字段，计划页却展示：计划类型、账户数、CID数、素材数、素材组数、预计项目数、校验状态、提交状态、创建时间，全部永远为“—”；点击“查看”打开的也不是 PlanSpec，而是台账摘要，且 IAA/9.9/2.9 链接、抖音号、预设、产品库、专辑ID 全部写死“—”。

证据：
- `dashboard/src/app/stores/plan.ts` 的 `toPlanView` 与后端 `LedgerView` 字段对照
- `dashboard/src/widgets/plan-preview/PlanSpecPreview.vue` 中写死的 `value: "—"`

修复方向：V1 如不交付 PlanSpec，应把该页面标记为“建设中”并只展示已落库字段；否则补齐 PlanSpec 查询接口。

### P0-4 规则模拟与编辑展示的不是真实规则

- 价格模板表单和右侧“规则模拟”使用前端写死的 2.9/9.9 默认值，页面说明是“按当前启用价格模板实时计算”，实际从不加载数据库 `template_price_rule`，也不调用已实现的后端 `/rules/simulate-price`（store 里 `simulatePrice` 无任何组件使用）。
- 素材规则编辑器同样写死两行默认区间，数据库里实际有 5 条（含 61-90、测试户区间），页面不展示；用户一旦点“保存草稿”，会拿默认值覆盖真实配置，存在数据丢失风险。

证据：
- `dashboard/src/pages/rules/index.vue` 中本地 `priceRules` 常量
- `dashboard/src/features/rule-editor/RuleEditor.vue` 中 `materialRows` 常量
- `dashboard/src/widgets/rule-simulator/RuleSimulator.vue` 使用本地 `simulatePriceCandidates`
- 数据库 `template_price_rule` 2 条、`material_rule_range` 5 条

### P0-5 队列页统计与分页口径误导

`/queue` 返回全量历史（含 COMPLETED/CANCELLED），前端：

- “队列 N 项”和分页总数包含已完成/已取消项，但分组列表只显示 7 种状态，这些项永远看不到；
- 分页先切片再按状态分组，翻页后同一状态的任务会被拆散，分组计数和总数对不上；
- Worker 状态面板从全量历史里找第一条 RUNNING/CLAIMED，可能抓到非今天的历史任务，导致“当前锁定任务”显示“—”或错误任务。

证据：
- `dashboard/src/widgets/queue-monitor/QueueMonitor.vue` 的 `GROUPS` 与 `items.length`
- `dashboard/src/pages/queue/index.vue` 的 `pagedItems` 先切片
- `backend/src/backend/interfaces/api/routes/queue.py` 的 `list_queue` 无状态/日期过滤

修复方向：队列接口按“活跃状态 + 今天”过滤；分页放在分组之后；Worker 当前任务按租约而非全量历史第一条。

## 3. P1 问题

### P1-1 系统记录标签页无法切换

`records/index.vue` 使用 `:model-value="ACTIVE_TAB"` 常量且无更新事件，点击“工作流运行/步骤记录/操作审计/配置变更/截图与文件/资源清理”都不会切换，始终停在“业务台账”。

### P1-2 任务详情抽屉 6 个页签是空占位

账户、外部资产、PlanSpec、异常、执行记录页签全部是固定空文案；执行时间线从不传 `timeline` 数据，永远显示“暂无执行记录”；推广链接卡片由 `detailLinks` 造出全“—”假数据。

### P1-3 异常中心操作全部占位，截图字段前后端不一致

- 除“修改配置”跳规则页外，重新检测、继续执行、重新登录、查看截图都提示“V1 待接入后端”；
- 前端用 `screenshot_urls`，后端 schema 叫 `screenshots`，且两端都不填值，截图永远“暂无”；
- `related_config`、`page_url`、`suggested_steps` 后端均无数据来源，详情区永远显示默认文案；
- 列表“步骤”列显示的是 `event_type`（如 EXECUTION_ERROR），不是业务步骤名。

### P1-4 产物“打开文件”必然 404

`ArtifactViewer.vue` 生成 `/api/artifacts/<path>` 链接，后端只有 `/api/records/artifacts` 元数据接口，没有任何文件下载/静态托管路由。

### P1-5 Worker 状态永远显示离线

`/healthz` 硬编码 `worker_heartbeat: False`，页面却以实时状态样式展示“Worker 状态/心跳”，顶部栏直接显示原始字符串 `False`。这是占位被当作真实状态展示。

### P1-6 同步飞书、导出按钮无实现

两个高频业务按钮只弹“后续阶段接入”提示，但按钮样式与真实操作一致，甲方会误以为功能可用。

### P1-7 队列页部分高风险操作无后端

“释放锁”“强制停止”按钮正常展示并进入确认框，确认后提示“接口待后端接入”；后端仅实现 pause/resume/cancel/retry。

## 4. P2 问题

1. 平台列直接显示 `TOMATO` / `JUBIAN` 英文码，业务上应显示“番茄 / 剧变”；平台筛选项在无数据时 fallback 中文、有数据后变英文，口径不一致。
2. 今日任务“更多”菜单不按任务状态禁用：未入队任务也显示“暂停/重试当前步骤”，点了报“任务未入队”；“重试当前步骤”语义与后端 retry 不一致。
3. 工作流“当前步骤”由 `queueStateToStep` 硬编码映射（QUEUED→飞书、CLAIMED→剧目资源、RUNNING→推广配置），与实际步骤无真实关联；RETRY_WAIT/PAUSED/MANUAL_REVIEW 显示“—”。
4. 首页 Worker 在线判断只认 `"ok"`，队列页认 `true/"ok"/"online"/"1"`，两处口径不一致。
5. 系统记录台账中的飞书行、专辑ID、产品ID、配置版本后端有库字段但不返回，页面永远“—”。
6. 全站无自动刷新/轮询，与 UI 计划“当前任务 5 秒轮询、Worker 心跳 5 秒轮询”不符，运行中状态需要手动刷新才能看到。

## 5. 项目文件整理

```text
short-drama-delivery-workbuddy/
├── dashboard/                  Vue 3 + Element Plus + Pinia 前端
│   ├── src/app/                router、Pinia stores、layouts
│   ├── src/pages/              7 个一级页面（workspace/tasks/queue/plans/rules/exceptions/records）
│   ├── src/widgets/            任务表格、队列监控、工作流时间线、规则模拟、计划预览、产物查看等
│   ├── src/features/           任务控制、规则编辑/发布、异常处理
│   ├── src/entities/           任务类型与展示辅助（状态/步骤/链接映射）
│   ├── src/shared/             API 客户端、错误映射、状态/格式化工具、UI 基础组件
│   └── tests/unit/             12 个测试文件、70 个用例（纯函数/组件级）
├── backend/                    FastAPI 后端
│   └── src/backend/
│       ├── interfaces/api/     routes + schemas（前后端契约所在层）
│       ├── application/        services（调度、队列、规则、Session、账户分配等）
│       ├── domain/             任务/队列/规则/执行/台账领域模型与状态机
│       ├── infrastructure/     SQLite ORM、仓储、迁移、日志
│       └── platforms/          feishu/tomato/delivery/ocean + mock 适配器
├── docs/                       设计、计划、架构、规则、工作流、资产清单
├── configs/                    投放配置快照与设置
├── data/                       app.db、Session 持久化、数据库备份
└── scripts/                    启动、验证、生产校验脚本
```

关键文件：

- 前后端契约：`backend/src/backend/interfaces/api/schemas.py`
- 前端数据入口：`dashboard/src/app/stores/*`
- 状态/格式化映射：`dashboard/src/entities/task/types.ts`、`dashboard/src/shared/utils/*`
- 前端 UI 计划：`docs/plans/frontend-ui-development-plan.md`

## 6. 验收对照（UI 计划 vs 现状）

| UI 计划验收项 | 现状 |
|---|---|
| 用户能清楚看到任务当前步骤 | 硬编码映射，非真实步骤，多状态显示“—” |
| 用户能查询链接来源和流转 | 详情卡片全为“—”占位 |
| 用户能查看飞书账户实时状态 | 详情页签为固定占位文案 |
| 用户能安全修改价格和素材规则 | 编辑区不加载真实规则，存在默认值覆盖风险 |
| 发布规则前看到真实模拟结果 | 模拟器用前端写死规则，未接后端 |
| 用户能查看 PlanSpec 并理解校验失败原因 | 计划页全部“—”，预览非 PlanSpec |
| 用户始终知道最终提交是否开启 | Dry Run 横幅存在，但 Worker 等状态仍展示占位值 |

## 7. 建议修复顺序

1. 统一时区与日期筛选（P0-1），这是所有页面可信度的基础。
2. 前后端契约对齐：任务详情字段、台账字段、PlanSpec 接口（P0-2/P0-3）。
3. 规则模拟接后端、编辑区从版本 payload 加载（P0-4）。
4. 队列按活跃状态过滤、分组后分页（P0-5）。
5. 修复系统记录页签、产物下载路由、异常字段名与动作（P1-1/3/4）。
6. 占位功能统一标记为“建设中”，不允许伪装成真实状态（P1-5/6/7、P2-5）。
7. 补充页面级与前后端契约测试；当前 70 个单测全部通过，但未覆盖以上展示问题。

## 8. 修复记录（2026-08-07）

本报告发现的问题已按以下方式修复并验证：

### 已修复

- P0-1 时间显示与日期筛选：后端任务日期筛选改为东八区日界；前端统一把 naive UTC 按 UTC 解析后转本地显示。
- P0-2 任务表空列：移除无数据源的 IAA/9.9/2.9、专辑ID、产品库、PlanSpec、计划状态、当前阶段列；详情抽屉只展示真实字段。
- P0-3 计划管理空数据：台账接口补齐 飞书行/专辑ID/产品ID/配置版本；计划页与预览只展示真实台账字段，去掉伪造的 PlanSpec 区块。
- P0-4 规则模拟与编辑：新增 `/api/rules/price-rules`、`/api/rules/material-rules` 读取真实生效规则；模拟器改调后端 `/api/rules/simulate-price`；价格/素材草稿在发布时写入规则表供 Worker 使用；素材规则无对应规则集时禁止保存并提示。
- P0-5 队列口径：`/api/queue` 默认排除 COMPLETED/CANCELLED；队列页去掉先切片后分组的逻辑，改为全部活跃项分组展示；Worker 当前任务按未过期租约识别。
- P1-1 系统记录页签：改为 `v-model` 可切换。
- P1-2 任务详情占位页签：只保留概览与执行时间线，时间线接入 `/api/records/events?task_id=` 真实事件。
- P1-3 异常中心：字段名与后端统一为 `screenshots`；后端补充业务步骤映射与任务截图路径；移除未实现的动作按钮。
- P1-4 产物下载：新增 `/api/artifacts/{path}` 文件路由（限制在 data 目录内）。
- P1-5 Worker 心跳：`/healthz` 改为按 worker_lease 活跃租约返回真实心跳；顶部栏显示在线/离线中文。
- P1-6 同步飞书/导出占位按钮：已移除。
- P1-7 队列未实现高风险操作：释放锁/强制停止按钮已移除。
- P2-1 平台标签：TOMATO/JUBIAN 统一显示番茄/剧变。
- P2-2 更多菜单：按任务队列状态过滤可执行操作。
- P2-3 步骤映射：移除硬编码的“当前步骤”展示。
- P2-4 Worker 在线判断：统一收敛到 system store 的 `isWorkerOnline()`。
- P2-5 台账缺失字段：后端返回真实字段，页面不再显示永远为空的列。

### 验证结果

- backend pytest：610 passed
- dashboard vitest：13 个测试文件、77 passed
- dashboard `npm run build`：通过（Element Plus 主包约 953KB 的 chunk 体积告警仍在）

### 遗留说明

- 自动轮询/5 秒刷新未在本轮实现，仍为手动刷新。
- 飞书账户实时数据、JUBIAN 表内链接、PlanSpec 结构化数据源尚未落地，相关界面按“无数据源不展示”处理，后续接入真实接口后再开放。
