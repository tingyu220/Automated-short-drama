# 公用剧目导入私有剧目表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Dashboard 中提供“读取今日剧目”操作，按北京时间从公用表读取当天剧目，转换后插入私有表顶部，并让后续自动提链只读取私有表。

**Architecture:** 新增独立的剧目导入用例，不让公用表直接参与自动提链。公用表只读，私有表作为执行事实源；导入服务负责字段映射、当天行识别、幂等去重和预览确认，飞书适配器负责读取、顶部插入、样式继承与回读校验。导入阶段保持公用表原始行序和 E 列原值；现有 `DeliveryScheduler`、链接准备和投放系统流程继续消费私有表，并在任务到点判断时按北京时间解析 E 列。

**Tech Stack:** Python 3、FastAPI、SQLAlchemy、lark-cli sheets、Vue 3、Pinia、Element Plus、pytest、Vitest。

## Global Constraints

- 所有业务日期使用北京时间（`Asia/Shanghai`，UTC+8）；前端不能使用浏览器本地时区推导业务日。
- 导入阶段不转换、不格式化 E 列时间；公用表显示什么值，私有表就原样写入什么值。
- 当天剧目的排列完全沿用公用表从上到下的行序，禁止在导入层按剧名、平台或本地解析后的时间重新排序。
- 只有后台扫描和提链接的到点判断可以解析私有表 E 列，并且必须按北京时间解释。
- 公用表只读；任何私有表写入必须经过“预览 → 用户确认 → 批量写入 → 回读校验”。
- 新行必须插入私有表第 2 行，过去剧目下移；写入行继承私有表原第 2 行的样式、边框和行高。
- 导入必须幂等；重复点击不能重复插入，唯一键优先使用来源行标识，备用键为标准化剧名 + 平台 + 北京时间上线分钟。
- 当前链接准备终点仍为 `LINK_READY`；导入不自动绕过上线时间，也不执行计划提交。
- 修改代码遵循 TDD：先写失败测试，再写最小实现，再运行完整验证。
- 不删除现有文件，不修改公用表，不覆盖私有表已有剧目和链接。

## 已核对的在线表结构

- 公用表：`PYQLw4lD5iUkmokRe6fcdSDenLc`，Sheet `漫剧投放计划表`，`sheet_id=sM4NAq`，28 列，当前 13185 行。
- 私有表：`Z0p3wf26Mi7ZxWkHIQ0c5D3SnGc`，Sheet `剧目表`，`sheet_id=a8d032`，14 列，当前有效剧目 6 行，空白区从第 8 行开始。
- 核对日：北京时间 `2026-08-17` 时公用表第 4～73 行共 70 行；实现时日期必须动态取北京时间，不得写死该日期。

## 字段映射

以已核对的列语义为准，映射由配置集中维护，禁止散落在路由或页面代码中：

| 公用表 | 私有表 | 处理 |
|---|---|---|
| A 测试组值（当前表头为 `0`） | A 测试组重点剧/2个测试户 | 原样复制 |
| B 备注 | B 备注 | 原样复制 |
| C 推广内容配置 | C 推广内容配置 | 原样复制 |
| D 是否已看 | D 是否已看 | 原样复制 |
| E 免费日期/追加测试标黄 | E 免费日期/追加测试标黄 | 原样复制，不转换格式、不调整分钟 |
| F 剧名 | F 剧名 | 必填，去除首尾空格 |
| J 备注 | G 备注 | 原样复制；公用表 G/H/I 不写入私有表 |
| K 平台 | H 平台 | `番茄` → `番茄`，`剧变` → `剧变` |
| L 剧集性质 | I 剧集性质 | 原样复制 |
| M 端 iaa 链接 | J 端 iaa 链接 | 原样复制 |
| N 绯色 b1-9.9 全 | K 绯色 b1-9.9 全 | 原样复制 |
| O 绯色 b2-2.9 全 | L 绯色 b2-2.9 全 | 原样复制 |
| V 田雨 | M 田雨 | 原样复制；忽略其他投手列 |
| AB IAA 校验 | N IAA 校验 | 原样复制 |

导入时若来源行已有链接且 `N=OK`，同时把任务初始化为已验证链接快照，后续不得重复提取；没有完整有效链接或 `N` 不是 `OK` 的行仍按上线时间进入链接准备流程。

### Task 1: 建立导入领域模型与字段转换器

**Files:**
- Create: `backend/src/backend/domain/imports/drama_import.py`
- Test: `backend/tests/unit/test_drama_import.py`

**Interfaces:**
- `PublicDramaRow`：来源行号、来源字段和 E 列原始时间文本；导入层不生成转换后的时间值。
- `PrivateDramaRow`：14 列目标值、来源唯一键、是否已有有效链接。
- `DramaImportPreview`：`source_count`、`new_count`、`duplicate_count`、`invalid_count`、`rows`、`errors`。
- `normalize_public_row(row, source_workbook, source_sheet_id) -> PrivateDramaRow | ImportRowError`。
- `build_import_preview(public_rows, private_rows, business_day) -> DramaImportPreview`：按北京时间业务日识别 E 列属于当天的行，但输出仍保留 E 列原值和来源行序。

- [ ] **Step 1: Write the failing tests**
  - 验证上述 14 列映射，尤其是公用表 `J→G`、`K→H`、`L→I`、`M/N/O→J/K/L`、`V→M`、`AB→N`。
  - 验证北京时间业务日识别、E 列原样保留、来源行序不变、空剧名/空时间的异常记录和标准化键去重。
  - 验证来源链接和 `N=OK` 时生成 `VALIDATED` 快照。
- [ ] **Step 2: Run `pytest backend/tests/unit/test_drama_import.py -v` and confirm failure**。
- [ ] **Step 3: Implement the model and converter**，只处理纯数据，不调用 lark-cli、数据库或 FastAPI。
- [ ] **Step 4: Run the focused tests and confirm pass**。
- [ ] **Step 5: Run `pytest backend/tests/unit/test_sheet_parser.py backend/tests/unit/test_drama_import.py -v`**。

### Task 2: 扩展飞书 Adapter，支持双表读取与私有表顶部插入

**Files:**
- Modify: `backend/src/backend/domain/ports/adapters.py`
- Modify: `backend/src/backend/platforms/feishu/feishu_adapter.py`
- Create: `backend/src/backend/platforms/feishu/drama_sheet_adapter.py`
- Modify: `backend/src/backend/bootstrap/adapters.py`
- Modify: `backend/src/backend/infrastructure/config/settings.py`
- Test: `backend/tests/unit/test_drama_sheet_adapter.py`

**Interfaces:**
- `DramaSheetAdapter.read_public_rows(day: date) -> list[PublicDramaRow]`：读取公用表完整有效区域，识别北京时间当天行；返回顺序必须与公用表行号升序一致，E 列保持原值。
- `DramaSheetAdapter.read_private_rows() -> list[PrivateDramaRow]`：读取私有表实际末行，不以固定 `N` 行截断。
- `DramaSheetAdapter.insert_private_rows(rows: list[PrivateDramaRow], expected_revision: int) -> InsertResult`：第 2 行开始批量插入并回读。
- `InsertResult`：插入行号、写入数、跳过数、回读校验结果。

- [ ] **Step 1: Write failing adapter tests**，验证两张表 URL/Sheet ID 分开使用、读取 70 行、E 列字面值不变、顺序与公用表一致、插入起点为 `A2`、重复行不写入、失败时不继续写入。
- [ ] **Step 2: Run focused tests and confirm failure**。
- [ ] **Step 3: Implement read paths**：公用表读取 `A1:AB<真实末行>`，私有表读取 `A1:N<真实末行>`，始终按 `[row=N]` 定位实际行号。
- [ ] **Step 4: Implement insertion**：先读取私有表第 2 行样式/边框/行高，插入足量行，批量写入 A:N，继承样式，并回读新增区校验关键字段。
- [ ] **Step 5: Run adapter tests and existing Feishu adapter tests**。

配置项：

```text
WORKBUDDY_FEISHU_SOURCE_SHEET_URL
WORKBUDDY_FEISHU_SOURCE_SHEET_ID=sM4NAq
WORKBUDDY_FEISHU_SOURCE_SHEET_NAME=漫剧投放计划表
WORKBUDDY_FEISHU_PRIVATE_SHEET_URL
WORKBUDDY_FEISHU_PRIVATE_SHEET_ID=a8d032
WORKBUDDY_FEISHU_PRIVATE_SHEET_NAME=剧目表
```

现有 `WORKBUDDY_FEISHU_TASK_SHEET_*` 在兼容期内作为私有表配置别名；真实模式缺少任一来源/目标配置时启动失败并返回明确错误。

### Task 3: 实现导入用例、预览确认和导入日志

**Files:**
- Create: `backend/src/backend/application/services/drama_import_service.py`
- Modify: `backend/src/backend/interfaces/api/schemas.py`
- Create: `backend/src/backend/interfaces/api/routes/drama_import.py`
- Modify: `backend/src/backend/interfaces/api/main.py`
- Modify: `backend/src/backend/infrastructure/database/models/task.py`
- Modify: `backend/src/backend/infrastructure/database/repositories/task_repository.py`
- Test: `backend/tests/unit/test_drama_import_service.py`
- Test: `backend/tests/api/test_drama_import_routes.py`

**Interfaces:**
- `POST /drama-import/preview` body `{ "business_date": "YYYY-MM-DD" }`，返回预览 ID和统计。
- `POST /drama-import/confirm` body `{ "preview_id": "..." }`，确认后执行唯一一次导入。
- `GET /drama-import/runs/{run_id}` 返回导入统计、错误和写入行号。
- `DramaImportService.preview(business_date: date) -> DramaImportPreview`。
- `DramaImportService.confirm(preview_id: str) -> ImportRunResult`。

- [ ] **Step 1: Write failing service/API tests**：预览只读、确认才写、同一预览重复确认返回幂等结果、并发确认只成功一次。
- [ ] **Step 2: Run focused tests and confirm failure**。
- [ ] **Step 3: Implement service transaction**：读取公用表与私有表 → 转换 → 预览持久化 → 确认时校验版本/末行未变化 → 批量插入 → 回读 → 写本地导入日志。
- [ ] **Step 4: Update task identity**：新增 `source_key` 与 `sheet_row` 分离；任务唯一查询优先 `source_key`，回填仍使用私有表实际行号。
- [ ] **Step 5: Run service/API tests and all backend tests**。

导入写入规则：新行在私有表第 2 行按公用表从上到下的原始行序一次性写入，原有第 2 行及之后的数据整体下移；不得在导入层二次排序。E 列原样复制，不把公用表的其他投手列、素材统计列、原名列写进私有表。

### Task 4: 让扫描和链接准备只消费私有表，并正确复用已有链接

**Files:**
- Modify: `backend/src/backend/platforms/feishu/sheet_parser.py`
- Modify: `backend/src/backend/application/services/delivery_scheduler.py`
- Modify: `backend/src/backend/application/services/task_preparation_service.py`
- Modify: `backend/src/backend/bootstrap/control_server.py`
- Modify: `backend/src/backend/bootstrap/automation_worker.py`
- Test: `backend/tests/unit/test_delivery_scheduler.py`
- Test: `backend/tests/unit/test_task_preparation_service.py`

- [ ] **Step 1: Add failing tests**：扫描只读私有 URL；同一 `source_key` 不重复建任务；来源 `J/K/L` 已有完整链接且 N=OK 时不访问番茄；后台把私有表 E 列按北京时间解析，链接缺失时必须等到该时间才执行。
- [ ] **Step 2: Run focused tests and confirm failure**。
- [ ] **Step 3: Implement private-source scheduler and link snapshot initialization**：时间解析只存在于私有表任务扫描/执行边界，解析结果统一转换为 UTC 存库，表内原始值不回写、不改格式。
- [ ] **Step 4: Run focused tests and existing workflow tests**。
- [ ] **Step 5: Run full backend test suite and migration check**。

### Task 5: Dashboard 增加“读取今日剧目”预览确认流程

**Files:**
- Modify: `dashboard/src/app/stores/task.ts`
- Modify: `dashboard/src/pages/tasks/index.vue`
- Create: `dashboard/src/features/drama-import/DramaImportDialog.vue`
- Create: `dashboard/src/entities/drama-import/types.ts`
- Test: `dashboard/src/features/drama-import/DramaImportDialog.spec.ts`
- Test: `dashboard/src/pages/tasks/index.spec.ts`

**Interfaces:**
- Pinia actions `previewTodayImport(date: string)`、`confirmImport(previewId: string)`、`fetchImportRun(runId: string)`。
- 页面按钮默认传北京时间日期；接口返回的日期和统计直接展示，不在前端二次换时区。

- [ ] **Step 1: Write failing component/store tests**：按钮存在、预览显示 70 条统计、异常行可查看、取消不写、确认后刷新任务列表。
- [ ] **Step 2: Run dashboard focused tests and confirm failure**。
- [ ] **Step 3: Implement dialog and store actions**：导入按钮与刷新/批量搭建并列，使用清晰的“读取今日剧目”“确认导入”文案。
- [ ] **Step 4: Run focused tests and dashboard build**。
- [ ] **Step 5: Run full dashboard test suite**。

### Task 6: 配置、文档和验收

**Files:**
- Modify: `.env.example`（若存在；不得改写用户 `.env` 密值）
- Modify: `docs/architecture/system-architecture.md`
- Modify: `docs/workflows/full-workflow.md`
- Create: `docs/production-validation-runbook-drama-import.md`
- Test: `backend/tests/integration/test_drama_import_flow.py`

- [ ] **Step 1: Add integration tests**：北京时间跨日、空数据、重复导入、已有链接复用、顶部插入顺序、回读不一致进入人工处理。
- [ ] **Step 2: Run integration tests and confirm failure**。
- [ ] **Step 3: Document the two-sheet configuration and operator workflow**。
- [ ] **Step 4: Run backend tests, dashboard tests, dashboard production build, and `git status`**。
- [ ] **Step 5: Show changed files and validation results; ask 老大确认后再创建中文 Git commit，不自动推送远程仓库**。

## 验收标准

1. 点击“读取今日剧目”只读取公用表，不会写公用表，也不会直接访问番茄或投放系统。
2. 预览统计准确，重复点击不会重复插入。
3. 新剧目始终插入私有表第 2 行，顺序与公用表从上到下完全一致；旧剧目下移，私有表原有格式保持不变。
4. 两张表字段按映射写入，公用表额外列不会错位污染私有表。
5. 导入时 E 列原样复制；后台运行时才按北京时间解析上线时间，北京时间零点前后不会误取相邻日期。
6. 后续扫描、提链、投放系统搭建只读取私有表；公用表不可作为执行数据源。
7. 公用表已有有效链接的剧目不会重复提取；番茄已有链接遵守原有搜索复用规则。
8. 后续目标仍可选择“仅提取链接”或“搭建链接完成”，本次导入不改变阶段控制。
