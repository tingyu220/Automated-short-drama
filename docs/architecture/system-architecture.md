# 短剧投放全流程自动化工作台 系统架构文档

## 1. 文档说明

本文档描述短剧投放全流程自动化工作台 V1 的模块化单体架构，定义进程边界、分层边界、关键接口与禁止依赖规则。本文档与 `docs/superpowers/specs/2026-08-06-short-drama-delivery-design.md` 保持一致，是后续 Phase 实施的技术约束来源。

## 2. 总体架构

系统采用模块化单体：一个 Python 后端进程内同时运行 Control Server 与 Automation Worker，共享同一套 Application、Domain、Platforms、Infrastructure 模块；前端为 Vue 3 单页应用，通过 FastAPI 接口访问。

```text
interfaces/api + interfaces/cli + interfaces/agent
        ↓
application/services + workflows + commands + queries + ports
        ↓
domain/tasks + queue + workflow + rules + plans + assets + errors
        ↓
platforms/feishu + tomato + delivery_system + ocean_engine
        ↓
infrastructure/database + browser + queue + logging + artifacts + config
```

固定约束：

- 依赖方向只允许上层指向下层，禁止反向依赖；
- Domain 不依赖 Playwright、FastAPI、数据库实现；
- Repository 接口不依赖 SQLite，未来可替换为 PostgreSQL；
- 平台写操作由 Automation Worker 单线程串行执行；
- 所有动态业务参数从规则版本和配置快照读取；
- 页面选择器等易变配置通过 Adapter 与 JSON 配置隔离，不写死在业务代码中。

## 3. 分层边界

### 3.1 Domain

领域层包含 `tasks`、`queue`、`workflow`、`rules`、`plans`、`assets`、`errors` 子模块，承载纯业务规则：

- 任务状态机与队列状态机；
- 链接状态流转与链接长度判定；
- 账户完整块分配、同日 CID 占用、测试户挑选；
- 素材常规/测试户分组计算；
- 命名模板渲染与 PlanSpec 校验；
- 配置规则版本与配置快照的领域模型。

Domain 只依赖 Python 标准库与领域模型自身，不依赖任何外部框架或平台 SDK。

### 3.2 Application

应用层包含 `services`、`workflows`、`commands`、`queries`、`ports`，负责用例编排、事务边界与状态机流转：

- `commands`：入队、暂停/恢复、重试、人工处理等写操作；
- `queries`：任务、队列、异常、规则、链接来源等只读查询；
- `workflows`：链接提取、账户分配、计划生成、状态轮询等编排；
- `ports`：声明 Repository 接口与 Adapter 接口，供 Domain 与 Application 使用。

Application 不包含平台操作细节，也不直接访问数据库或浏览器。

### 3.3 Platforms

平台层为每个外部系统提供 Adapter 与 Page Object：

- `FeishuAdapter`：剧目表/账户表读写、N 状态读取、链接回填、M 写入；
- `TomatoAdapter`：番茄搜索、登录态、免费/付费入口、链接提取；
- `DeliverySystemAdapter`：剧目资源、推广内容配置、计划提交、任务状态轮询；
- `OceanEngineAdapter`：巨量产品库建产品（V1 先 Mock，后接真实平台）。

每个平台先 Mock，再只读验证，再“填写但不提交”，最后单条/批次提交；每个平台独立持久化浏览器 Session。

### 3.4 Infrastructure

基础设施层实现 Repository 接口与 Adapter 接口：

- `database`：SQLAlchemy 2 + SQLite + Alembic，持久化领域模型；
- `browser`：Playwright 浏览器封装、登录态与 Session 管理；
- `queue`：队列租约、心跳、崩溃恢复；
- `logging`：本地操作日志与 ExecutionEvent 持久化；
- `artifacts`：截图与文件产物；
- `config`：defaults JSON 只读初始化、SQLite 生效配置、exports JSON 导出备份。

### 3.5 Interfaces

`interfaces/api` 暴露 FastAPI 路由；`interfaces/cli` 提供命令行入口；`interfaces/agent` 提供浏览器应用模式入口。Interfaces 只负责协议转换，不承载业务规则。

## 4. Control Server

Control Server 是常驻的 FastAPI 进程，职责：

- 提供 Dashboard 所需的查询与命令 API；
- 启动时立即扫描当天任务（按 `sheet_row + drama_name` 去重），每小时增量扫描；
- 任务到投放时间后入队；
- 提供规则与配置中心的编辑、校验、发布接口；
- 提供手动入队、暂停/恢复、失败重试、人工处理入口；
- 不直接修改数据库，不执行平台写操作；
- 账户可视化实时读取飞书账户表，不维护第二套账户数据。

Control Server 通过 Application 的 `commands` 与 `queries` 访问系统，由 Infrastructure 完成持久化。

## 5. Automation Worker

Automation Worker 是同一进程内的后台执行体，V1 固定单 Worker：

- 从队列领取任务，建立租约并持续心跳；
- 按平台分流执行端到端流程：番茄链接提取与回填、投放系统资源与推广配置、巨量产品库建产品、PlanSpec 生成与提交保护、状态轮询与 M 写入；
- 平台写操作串行执行；
- 创建类操作超时先对账，禁止直接重复提交；
- 失败、部分失败、超时进入 `MANUAL_REVIEW` 并记录异常与截图；
- 完成后清理活动队列项，保留台账与日志。

Worker 通过 Adapter 接口操作平台，通过 Repository 接口持久化，不直接访问 Dashboard。

## 6. Repository 接口

Repository 接口在 Application `ports` 中声明，由 Infrastructure 实现；接口只使用领域模型，不暴露 SQLAlchemy、SQLite 或任何数据库类型。

| 接口 | 主要方法 | 对应领域模型 |
|---|---|---|
| `TaskRepository` | `get_by_key`、`save`、`list_today` | `DramaTask` |
| `QueueRepository` | `enqueue`、`claim`、`heartbeat`、`release`、`list_active` | `QueueItem` |
| `WorkflowRepository` | `start_run`、`record_step`、`finish_run` | `WorkflowRun`、`StepRun` |
| `LedgerRepository` | `append`、`find_by_task` | `TaskLedger` |
| `LinkRepository` | `save_link`、`get_by_task`、`find_duplicate` | `PromotionLinkSet` |
| `AssetRepository` | `find_by_drama_album`、`save` | `DramaAsset` |
| `PlanSpecRepository` | `save`、`get_latest` | `PlanSpec` |
| `AccountRepository` | `save_usage`、`save_snapshot`、`save_allocation`、`find_allocation` | `AccountUsageRecord`、`AccountSheetSnapshot`、`AccountAllocation` |
| `ExecutionRepository` | `log_event`、`save_artifact` | `ExecutionEvent`、`ExecutionArtifact` |
| `RuleRepository` | `get_active`、`publish_version`、`save_snapshot`、`append_change_log` | `RuleSet`、`RuleVersion`、`ConfigSnapshot`、`ConfigChangeLog` |

Repository 接口方法按事务边界组织：读取返回领域模型，写入接收领域模型，幂等键由 Domain 规则保证。

## 7. Adapter 接口

Adapter 接口在 Application `ports` 中声明，由 Platforms 实现。接口只接收领域模型或平台无关的 DTO，不暴露平台私有类型。

### 7.1 FeishuAdapter

- `list_drama_rows()`：读取剧目表当天数据与 N 列状态；
- `read_account_sheets(kind)`：读取 iaa/iap/测试户账户表最新数据；
- `write_links(task, links)`：回填 J/K/L 链接；
- `write_completed(task)`：真实提交且状态完成后写 M=1；
- `read_back_row(task)`：写入后回读校验。

### 7.2 TomatoAdapter

- `search_drama(name)`：按剧名搜索；
- `extract_iaa(task)`：免费入口提取 IAA 链接；
- `extract_iap(task)`：付费入口扫描模板，提取 9.9/2.9 链接；
- `ensure_session()`：维护登录态与持久化 Session。

### 7.3 DeliverySystemAdapter

- `find_or_create_drama(drama_name, album_id)`：识别/创建剧目资源；
- `sync_promotion_configs(task, links)`：创建缺失的推广内容配置；
- `submit_plan(planspec)`：提交标准投放计划（受 `ALLOW_FINAL_SUBMIT` 保护）；
- `poll_status(task)`：轮询任务状态。

### 7.4 OceanEngineAdapter

- `create_product(drama, album_id)`：在巨量产品库建产品；
- `get_product_id(drama, album_id)`：查询已有产品，用于幂等对账。

V1 中 OceanEngineAdapter 只负责产品库，不负责标准计划状态判断；任务完成状态以投放系统巨量引擎 V2 任务页为最终来源。

## 8. 禁止依赖规则

以下规则为架构级强制约束，实施与评审必须遵守：

1. **Domain 不依赖 Playwright、FastAPI、数据库**：Domain 模块不得导入或引用浏览器、Web 框架、SQLAlchemy/SQLite 及任何平台 SDK；依赖方向由 Application `ports` 反转。
2. **Page Object 不更新任务状态**：Page Object 只负责页面元素的读取、填写与提交结果返回；任务/队列/链接状态流转只允许发生在 Application 编排层。
3. **Adapter 不决定账户与素材规则**：Adapter 只执行“读/写/提取/提交”的平台协议转换；账户整块分配、测试户挑选、素材分组、命名与 PlanSpec 校验等规则全部由 Domain 承载。
4. **Dashboard 不直接改库**：Dashboard 及所有 API 层只能调用 Application `commands`；数据库写入只能经由 Infrastructure 中的 Repository 实现。

## 9. 数据与状态流

```text
飞书剧目表 ─扫描→ Control Server 入队 → Automation Worker
    → Tomato/DeliverySystem/OceanEngine Adapter
    → Domain 规则校验 → Repository 持久化
    → 轮询完成 → 回写飞书 M=1 → 台账保留
```

规则与配置事实源：`configs/defaults/*.json` 只读初始化 → SQLite 生效配置 → `configs/exports/*.json` 导出备份；新任务读取已发布 RuleVersion，运行中任务继续使用自己的 ConfigSnapshot。

## 10. 一致性要求

- 本文档不含任何未完成项占位符；
- 与设计文档的已确认决策记录保持一致；
- 后续 Phase 对架构的调整必须回写本文档并保持依赖方向不变。
