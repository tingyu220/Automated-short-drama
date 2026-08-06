# 短剧投放全流程自动化工作台 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从空仓库开始，按模块化单体工程搭建短剧投放全流程自动化工作台，先完成 Phase 0 设计落盘与 Phase 1 工程骨架，再逐阶段实现持久化队列、双层状态机、规则配置中心、Dashboard、Mock Dry Run、真实平台 Adapter 与 PlanSpec。

**Architecture:** FastAPI Control Server + 独立 Automation Worker + SQLite 持久化队列 + Vue 3 Dashboard；Domain / Application / Platforms / Infrastructure 分层；平台能力全部走 Adapter，Mock 先行，真实平台按阶段接入。

**Tech Stack:** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + SQLite + Playwright + pytest；Vue 3 + Vite + TypeScript + Pinia + Vue Router + Element Plus + ECharts + Vitest；lark-cli；Git。

## Global Constraints

- 当前工作区 `D:\work\short-drama-delivery-workbuddy` 作为项目根；首次实施时执行 `git init`，远程连接、提交、推送前必须向用户确认，Commit Message 使用中文，推送使用 git bash。
- Windows 本地运行；默认 `ALLOW_FINAL_SUBMIT=false`；正式本地运行使用 FastAPI 托管前端静态文件，不用 Vite 开发服务器长期运行。
- 单 Automation Worker；单平台写操作串行；所有创建操作幂等，超时先对账再决定是否重试。
- Domain 不得导入 Playwright、FastAPI 或数据库实现；Repository 接口不依赖 SQLite，未来可替换 PostgreSQL。
- 配置事实源 = SQLite；`configs/defaults/*.json` 只读初始化；`configs/exports/*.json` 用于导出/备份/迁移。
- 飞书账户表是账户唯一业务事实源；Dashboard 不维护第二套账户数据；分配前必须重新读取飞书，写后回读确认。
- 链接禁止本地构造/拼接/猜测；番茄从页面提取，剧变从飞书表 J/K/L 直接读取。
- 每个功能按 TDD 执行：写失败测试 → 确认失败 → 最小实现 → 确认通过 → 提交。
- V1 不实现漫剧全域计划，只预留规则板块。
- 前端 UI 按独立子计划 `docs/plans/frontend-ui-development-plan.md` 执行。
- 删除操作先备份；数据库迁移/批量导入/高风险发布/手动清理前自动备份到 `data/backups/`。

## 计划边界与执行方式

- 本文件是总控计划；Phase 0 细化到文件级任务，Phase 1-9 每阶段启动前按 writing-plans 展开为任务级细则，不在本文件里塞入全部代码。
- 每个阶段完成后必须：运行测试与静态检查 → 输出文件变更清单 → 更新本计划 → 创建单一职责中文 Commit（提交前向用户确认）→ 不自动开始下一阶段。
- 前端阶段（UI-01 到 UI-08）以 `docs/plans/frontend-ui-development-plan.md` 为准。

---

## Phase 0：仓库审查与设计落盘

### Task 0.1 初始化仓库骨架

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `docs/README.md`

- [x] **Step 1：创建 `.gitignore`**

忽略 `data/`、`node_modules/`、`__pycache__/`、`.venv/`、`.env`、`*.pyc`、`dist/`、`coverage/`、`.pytest_cache/`。

- [x] **Step 2：创建 `README.md`**

包含项目名、本地启动方式、文档索引（架构/流程/规则/设计/计划）。

- [x] **Step 3：创建 `AGENTS.md`**

写入 Codex 开发规则：精简输出、先读文档再改代码、小提交、中文 Commit、删除前备份、TDD。

- [x] **Step 4：创建 `docs/README.md`**

列出现有文档入口。

- [x] **Step 5：执行 `git init`**

本地仓库初始化；远程连接/提交前向用户确认。

- [x] **Step 6：验证**

运行 `git status`，确认 `README.md`、`AGENTS.md`、`docs/` 均存在且未提交。

### Task 0.2 现有代码资产清单

**Files:**
- Create: `docs/current-code-inventory.md`

- [x] **Step 1：盘点 `D:\work\short drrama Analysis`**

记录 `FanqieCrawlerClient`（`drama_priority/crawlers/fanqie.py`）、`fanqie_bridge.py`、`fanqie_batch_crawl.py`、FastAPI 分析与前端，标注与新系统 `TomatoAdapter` 的映射。

- [x] **Step 2：盘点 `D:\work\聚赢\short-drama-monitor`**

记录畅读登录脚本、`changdu_crawler.py`、`fanqie_batch_verify.py`、`partial_failed_monitor.py`、`tjhaozew_monitor.js`，标注登录 Session、投放系统页面、巨量报表页面的复用方式。

- [x] **Step 3：验证路径与内容**

对清单中每个文件执行 `Test-Path`，确认存在；没有测试证明必须重写前，禁止直接推翻现有脚本。

- [x] **Step 4：提交**

`git add docs/current-code-inventory.md` 等，Commit Message：`docs: 输出现有代码资产清单`（提交前向用户确认）。

### Task 0.3 架构文档

**Files:**
- Create: `docs/architecture/system-architecture.md`

- [x] **Step 1：编写分层架构**

包含 Control Server、Automation Worker、Domain/Application/Platforms/Infrastructure 边界、Repository 接口、Adapter 接口。

- [x] **Step 2：编写禁止依赖规则**

Domain 不依赖 Playwright/FastAPI/数据库；Page Object 不更新任务状态；Adapter 不决定账户与素材规则；Dashboard 不直接改库。

- [x] **Step 3：验证**

文档内无 `TBD`/`TODO`；与设计文档、本计划无矛盾。

### Task 0.4 全流程文档

**Files:**
- Create: `docs/workflows/full-workflow.md`

- [x] **Step 1：编写主流程**

00:00 全量扫描 → 应用启动即时扫描 → 每小时增量扫描 → `WAITING_TIME` → 到点入队 → 番茄/剧变分流 → 链接提取/读取 → 剧目资源 → 推广内容配置 → 巨量产品库 → 账户块分配 → PlanSpec → 提交 → 轮询 → M=1 → 清活动记录留台账。

- [x] **Step 2：编写状态机与异常分支**

覆盖 `MANUAL_REVIEW`、重试、超时、部分写入、`RESULT_UNCERTAIN`、登录失效。

- [x] **Step 3：验证**

流程与设计文档一致，Dry Run 不写表/不提交/不写 M=1 的规则明确。

### Task 0.5 业务规则文档

**Files:**
- Create: `docs/rules/business-rules.md`

- [x] **Step 1：编写链接规则**

IAA 选集边界、IAP 模板区间与排序、剧变来源字段、链接状态、来源可追踪。

- [x] **Step 2：编写账户与素材规则**

账户块 `3+3+3+1` / `3+3`、空位扫描、追加块、测试户挑选、素材通铺与分组公式。

- [x] **Step 3：编写计划与完成规则**

标准计划固定字段、命名模板、CID 配置、PlanSpec 校验、巨量V2 状态为最终完成来源。

- [x] **Step 4：验证**

规则文档与设计文档冲突处以补充规范为准。

### Task 0.6 文档一致性自检

- [x] **Step 1：扫描占位符**

运行 `rg -n "TBD|TODO" docs/`，除明确开放项外不允许存在占位符。

- [x] **Step 2：交叉检查**

核对设计文档、前端 UI 子计划、业务规则、全流程、本计划五份文档，修正矛盾。

- [x] **Step 3：提交**

Commit Message：`docs: 完成Phase 0设计落盘`（提交前向用户确认）。

### Phase 0 验收标准

- 没有遗漏现有番茄登录与详情页脚本；
- 模块边界清晰，没有直接开始编写大型 RPA；
- 架构/流程/规则/计划可独立执行；
- 文档之间不存在矛盾。

---

## Phase 1：基础工程骨架

### Task 1.1 后端工程骨架

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/backend/__init__.py`、`domain/`、`application/`、`platforms/`、`infrastructure/`、`interfaces/`、`bootstrap/` 包
- Create: `backend/pytest.ini`

- [ ] 依赖固定：fastapi、uvicorn、pydantic v2、sqlalchemy 2、alembic、playwright、pytest、pytest-asyncio
- [ ] 空目录结构可被 pytest 收集
- [ ] 测试：`test_imports.py` 验证各包可导入

### Task 1.2 配置加载、日志与错误模型

**Files:**
- Create: `backend/src/backend/infrastructure/config/settings.py`
- Create: `backend/src/backend/infrastructure/logging/logger.py`
- Create: `backend/src/backend/domain/errors/domain_error.py`、`app_error.py`

- [ ] 配置从环境变量 + `configs/defaults/*.json` 读取，校验 `ALLOW_FINAL_SUBMIT` 等关键项
- [ ] 结构化 JSON 日志，日志不包含完整 Cookie/Token
- [ ] 统一错误类型与 HTTP 映射
- [ ] 测试：配置校验失败、日志脱敏、错误映射

### Task 1.3 SQLite 连接与 Alembic

**Files:**
- Create: `backend/src/backend/infrastructure/database/engine.py`、`base.py`
- Create: `backend/alembic.ini`、`backend/alembic/`
- Create: `backend/tests/integration/test_database.py`

- [ ] SQLite `journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`
- [ ] 数据库路径 `data/database/app.db`
- [ ] 迁移前自动备份到 `data/backups/`
- [ ] 测试：数据库创建、迁移执行、备份生成

### Task 1.4 FastAPI Control Server 与健康检查

**Files:**
- Create: `backend/src/backend/interfaces/api/main.py`
- Create: `backend/src/backend/bootstrap/control_server.py`
- Create: `backend/tests/unit/test_health_api.py`

- [ ] `GET /healthz` 返回 server/worker/db/config 状态
- [ ] `ALLOW_FINAL_SUBMIT=false` 在响应中可见
- [ ] 测试：健康检查 200、关闭状态正确

### Task 1.5 Automation Worker 启动与心跳

**Files:**
- Create: `backend/src/backend/bootstrap/automation_worker.py`
- Create: `backend/src/backend/application/services/worker_heartbeat.py`
- Create: `backend/tests/unit/test_worker_heartbeat.py`

- [ ] Worker 启动时登记心跳，周期更新
- [ ] 单 Worker 锁，启动时发现旧租约可恢复
- [ ] 测试：心跳写入、租约过期、重复启动保护

### Task 1.6 Vue Dashboard 工程骨架

**Files:**
- Create: `dashboard/package.json`、`vite.config.ts`、`tsconfig.json`
- Create: `dashboard/src/app/router/`、`app/layouts/`、`app/stores/`
- Create: `dashboard/src/pages/workspace|tasks|queue|plans|rules|exceptions|records/`
- Create: `dashboard/src/shared/styles/design-tokens.css`、`theme.css`

- [ ] 按前端子计划 UI-01/UI-02：设计 Token、深色侧边栏、顶部状态栏、七页路由
- [ ] `ALLOW_FINAL_SUBMIT=false` 时顶部固定显示 Dry Run 警示
- [ ] 测试：`npm run test`、`npm run build`

### Task 1.7 一键启动与正式运行

**Files:**
- Create: `scripts/start.ps1`
- Create: `scripts/start.bat`
- Create: `scripts/start-workbench.ps1`

- [ ] 开发模式：启动 FastAPI + Vite + Worker
- [ ] 正式模式：`npm run build` → FastAPI 托管静态文件 → 启动 Worker → `chrome --app=http://127.0.0.1:<port>`
- [ ] 验证：三个进程可启动、健康检查正常、应用模式窗口打开

### Phase 1 验收标准

- 后端可启动、前端可启动、Worker 可启动；
- 健康检查正常，前后端构建通过；
- Dry Run 开关全局可见；
- 一键启动脚本可运行。

---

## Phase 2：任务队列与双层状态机

**Models:** `DramaTask`、`QueueItem`、`WorkflowRun`、`StepRun`、`TaskLedger`、`WorkerLease`

**Tasks:**
- [ ] 队列状态机与排序规则
- [ ] 原子领取任务
- [ ] Worker 租约与心跳续租
- [ ] Worker 崩溃恢复
- [ ] 完成后出队并保留最小台账
- [ ] 失败重试、暂停、取消、人工处理

**Tests:** 原子领取、租约超时恢复、重复领取、去重入队、完成后台账保留。

**Acceptance:** 创建模拟任务 → 到点自动入队 → Worker 领取 → 模拟崩溃 → 租约超时 → 重启恢复 → 完成任务 → 活动队列删除 → 台账仍存在。

---

## Phase 3：资源生命周期与日志

**Models:** `ExecutionEvent`、`ExecutionArtifact`、`ResourceCleanupService`

**Tasks:**
- [ ] 执行事件与截图/文件产物持久化
- [ ] 日志保留策略
- [ ] 截图保留策略
- [ ] 临时目录清理
- [ ] 浏览器空闲释放
- [ ] 完成任务后释放锁与页面

**Tests:** 锁释放、无用页面关闭、临时文件删除、过期日志清理、外部 ID 与任务摘要可查询。

---

## Phase 4：动态规则与配置中心后端

**Models:** `RuleSet`、`RuleVersion`、`RuleParameter`、`MaterialRuleRange`、`TemplatePriceRule`、`AccountProfile`、`PresetMapping`、`DouyinAccount`、`PlatformResourceConfig`、`ConfigSnapshot`、`ConfigChangeLog`

**Tasks:**
- [ ] `configs/defaults/*.json` 首次初始化导入 SQLite
- [ ] 草稿编辑、保存、发布、版本历史
- [ ] 区间冲突校验
- [ ] 规则模拟（IAP 价格、素材分组）
- [ ] ConfigSnapshot 生成，运行中任务固定快照
- [ ] 配置变更审计

**Tests:** 区间冲突、模拟结果、版本发布、快照隔离、defaults 初始化幂等。

---

## Phase 5：Dashboard 与企业管理型 UI

**Backend APIs:**
- [ ] 任务/队列/计划/规则/异常/记录查询与操作 API
- [ ] 飞书账户实时读取与分配控制 API
- [ ] PlanSpec 预览与校验 API
- [ ] 配置草稿/发布/模拟 API

**Frontend:** 按 `docs/plans/frontend-ui-development-plan.md` 的 UI-01 到 UI-08 执行。

**Tests:** API 契约测试 + Vitest 组件/页面测试 + 构建验证。

---

## Phase 6：模拟平台与完整 Dry Run

**Adapters:** `MockFeishuAdapter`、`MockTomatoAdapter`、`MockDeliverySystemAdapter`、`MockOceanEngineAdapter`

**Tasks:**
- [ ] 模拟飞书任务与时间调度
- [ ] 模拟链接提取与 IAP 模板
- [ ] 模拟剧目资源/推广配置/产品库
- [ ] 生成 PlanSpec 并模拟提交
- [ ] 模拟重试、业务跳过、页面变化
- [ ] Dashboard 完整展示全流程

**Acceptance:** 不访问任何真实平台即可跑完整工作流；Dry Run 不写飞书表、不真提交、不写 M=1。

---

## Phase 7：真实平台 Adapter

接入顺序（禁止同时首次接入多个平台）：

1. 飞书 Lark CLI
2. 番茄 IAA 链接
3. 番茄 IAP 模板
4. 投放系统剧目资源
5. 投放系统推广内容
6. 巨量产品库
7. 标准投放页面

每个平台必须按：只读验证 → 填写但不提交 → 单条真实提交 → 批次提交。

**Tests:** 页面选择器变化捕获、`RESULT_UNCERTAIN` 对账、登录态失效处理、截图与异常记录。

---

## Phase 8：PlanSpec 与标准投放

**Rules:** `AccountRoutingRule`、`PromotionContentMappingRule`、`MaterialGroupRule`、`ProjectLimitRule`、`TaskNameRule`、`PlanValidationRule`

**提交前检查:**
- [ ] 端免端付未混合
- [ ] CID 映射正确
- [ ] 付费模板与 B1/B2 匹配
- [ ] 抖音号有效
- [ ] 开户预设完整
- [ ] 广告预设完整
- [ ] 素材全部选中
- [ ] 素材组计算正确
- [ ] 项目数正确
- [ ] 任务名称正确

**Acceptance:** `ALLOW_FINAL_SUBMIT=false` 时只生成 PlanSpec，不允许最终提交。

---

## Phase 9：生产验证

验证顺序（每一步通过后再扩大范围）：

1. 单部测试户
2. 单部端免
3. 单部端付仅 9.9
4. 单部端付仅 2.9
5. 单部端付双模板
6. 3 部剧
7. 5 部剧
8. 10 部剧

每个范围验证完成后保留台账与异常记录，更新生产验证报告。

---

## 全局测试与提交规则

- 严格 TDD：写失败测试 → 确认测试失败 → 最小实现 → 确认测试通过 → 提交；
- 每个提交只解决一个明确问题；
- Commit Message 使用中文；
- 提交前向用户确认；推送使用 git bash；
- 每阶段结束输出：测试结果、静态检查、文件变更清单、下一阶段入口；
- 未运行测试前不得声称功能完成。
