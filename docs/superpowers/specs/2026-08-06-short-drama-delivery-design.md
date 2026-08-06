# 短剧投放全流程自动化工作台 V1 设计文档

## 1. 项目定位与目标

本地运行的短剧投放全流程自动化工作台，负责：

- 从飞书剧目表读取任务，按投放时间自动入队；
- 从番茄平台提取 IAA / IAP 推广链接并回填飞书表；
- 将链接流转到投放系统：识别/创建剧目资源、推广内容配置、标准投放计划；
- 在巨量平台建立产品库并生成 PlanSpec；
- 轮询投放系统/巨量引擎 V2 任务状态，`已完成` 后回写飞书表完成标记；
- 通过企业级 Dashboard 提供任务、队列、规则、异常、日志的统一视图。

V1 目标不是“从页面点击开始”，而是先建立可恢复、可配置、可测试、可演进的模块化单体工程，再逐步接入真实平台。

## 2. V1 范围

### 2.1 做

- 飞书 Sheet 读写（剧目表、iaa账户、iap账户、测试户账户）；
- 任务队列与双层状态机、Worker 租约/心跳/崩溃恢复；
- 番茄链接提取（IAA + IAP）与回填；
- 投放系统剧目资源、推广内容配置；
- 巨量产品库建产品（先 Mock，后真实适配）；
- PlanSpec 生成与提交保护（默认 `ALLOW_FINAL_SUBMIT=false`）；
- 轮询任务状态，完成后写 M=1；
- Dashboard 工作台、今日任务、队列、计划管理、规则与配置、异常中心、系统记录；
- 规则与配置中心（SQLite 生效配置，defaults JSON 初始化，exports JSON 备份）；
- Dashboard 账户可视化（实时读取飞书账户表，不维护第二套账户数据）；
- 素材通铺选择与常规/测试户素材分组；
- 手动入队、暂停/恢复、失败重试、人工处理入口；
- 本地操作日志、截图、异常原因持久化。

### 2.2 暂不做（V1 保留但后续实现）

- 漫剧全域计划（预留规则板块）；
- 现有监控系统的 IAM/r3/巨量监控/watchdog 任务吸收；
- 飞书 IM 消息推送；
- 多用户账号体系；
- Electron/Tauri 桌面壳；
- 后台对 CID 广告预设/抖音号/开户预设的具体业务值录入（仅建结构，值由 Dashboard 后续维护）。

## 3. 技术栈与运行形态

- 后端：Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + SQLite
- 浏览器自动化：Playwright
- 测试：pytest + Vitest
- 前端：Vue 3 + Vite + TypeScript + Pinia + Vue Router + Element Plus + ECharts
- 飞书：`lark-cli`（`--as user`）
- 运行形态：Windows 本地；一键启动脚本拉起 FastAPI + Vue；浏览器应用模式（`--app=...`）打开独立无地址栏窗口；不做登录
- 配置：`configs/defaults/*.json` 只读默认模板；当前生效配置以 SQLite 为准；`configs/exports/*.json` 用于导出/备份/迁移

## 4. 总体架构

模块化单体，分层如下：

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

- Domain 不依赖 Playwright / FastAPI / 数据库实现；
- Repository 接口不依赖 SQLite，未来可替换 PostgreSQL；
- 平台写操作单 Worker 串行；
- 所有动态业务参数从规则版本和配置快照读取；
- 页面选择器、CID 配置等通过 Adapter + JSON 配置隔离，不写死在业务代码。

## 5. 端到端全流程

```text
00:00 扫描剧目表（记录当天投放任务）
→ 应用启动时立即扫描一次当天任务（去重，不重复创建）
→ 每小时增量扫描（补录当天新增行）
→ 任务 WAITING_TIME，等待 E 列投放时间
→ 到点 READY → QUEUED → Worker 领取
→ 按平台分流：
    番茄：搜索剧目 → 免费入口提取 IAA 链接
          → 付费入口扫描模板 → 提取 9.9/2.9 链接
    剧变：直接使用表内已有 J/K/L 链接，不进入番茄
→ 回填 J/K/L 到飞书剧目表（失败原因仅存本地）
→ 投放系统：识别/创建剧目资源（delivery_drama_id / album_id）
→ 推广内容配置：iaa-平台-剧名 / 9.9-平台-剧名 / 2.9-平台-剧名
→ 巨量产品库：创建剧目产品，产品 ID 进入 PlanSpec
→ 取账户：iaa/iap 账户表找第一个完整可用块，整块回填剧名
→ 生成 PlanSpec 并校验
→ 提交标准投放计划（ALLOW_FINAL_SUBMIT=true 时才真提交）
→ 每 5 分钟轮询投放系统/巨量V2 任务状态，最长 2 小时
→ 状态=已完成 → 写 M=1 → N 自动变 OK → 清理活动队列项，保留台账/日志
→ 失败/部分失败/超时 → MANUAL_REVIEW + 异常中心（本地原因、截图）
```

Dry Run / Mock 阶段不写飞书表、不真提交、不写 M=1。

## 6. 飞书数据结构

### 6.1 剧目表（Sheet1，A-N 共 14 列）

| 列 | 表头 | 用途 |
|---|---|---|
| A | 测试组重点剧/2个测试户 | 展示，不参与逻辑 |
| B | 备注 | 展示；跳过规则 V1 不做 |
| C | 推广内容配置 | 仅识别剧目归属人（取“-”前名字），不路由 |
| D | 是否已看 | 展示 |
| E | 免费日期/追加测试标黄 | 投放/可操作时间 `available_time` |
| F | 剧名 | 主键之一 |
| G | 备注 | 展示 |
| H | 平台 | 番茄 / 剧变，决定执行入口 |
| I | 剧集性质 | 展示 |
| J | 端iaa链接（优先卡一）/番茄卡第二集 | 回填 IAA 链接 |
| K | 绯色b1-9.9全 | 回填 9.9 链接 |
| L | 绯色b2-2.9全 | 回填 2.9 链接 |
| M | 田雨 | 完成时写 `1` |
| N | IAA校验 | 表内机制自动变 `OK` |

处理规则：

- 以 N 列判断：`OK` 跳过；`有人未上`/空则处理；
- E 时间未到不打开番茄、不搜索、不占页面；
- J/K/L 提取成功后回填；M=1 仅在“真实提交且巨量V2 状态=已完成”后写入；
- 失败原因不写表，只存本地 SQLite + `data/`。

### 6.2 iaa账户

列：`账户组 | 剧名 | 账户名称 | 账户ID/CID | 是否测试户 | 启用状态`（账户组可显式列，也可按块顺序识别）

- 账户组结构 V1 写死：`B1×3 + B4×3 + B7×3 + BX×1`；不写死物理行号、账户名称、CID；
- 一个块 = 同一剧名下连续 10 行，整块一起上一部剧；
- 分配：读取飞书最新数据 → 从上向下找第一个完整可用块（10 行剧名均空、全部启用、结构 3+3+3+1、同一 CID 当天未分配）→ 将当前剧名写入全部 10 行 → 回读确认；
- 只有部分行空白不算可用块；只写空剧名，绝不覆盖已有剧名；
- 同一 CID 当天不分配第二部剧；老块不覆盖，后续在表尾追加标准块（从最近完整启用块复制账户名称/CID/账户组/启用状态，不复制剧名/是否测试户/备注）；
- 测试户：从当前剧已分配的 B4 三行中选一个（启用、未标记、本批次未被其他测试任务使用），写 `是`；
- 测试户来源后续可配置为“测试户账户表 / IAA-B4 / 自动”。

### 6.3 iap账户

列：`账户组 | 剧名 | 账户名称 | 账户ID/CID | 是否测试户 | 启用状态 | 备注`

- 账户组结构 V1 写死：`B1-9.9×3 + B2-2.9×3`；
- 只有 9.9 → 找完整 B1-9.9 三行组并回填剧名；只有 2.9 → 找完整 B2-2.9 三行组；
- 同时有 9.9 和 2.9 → 必须同时找到两组（6 行）一起回填；只找到一组时不做部分分配，进 `MANUAL_REVIEW`；
- 无匹配模板 → 不分配 IAP 账户，属正常业务结果。

### 6.4 测试户账户

- 空表备用；与 IAA-B4 二选一作为测试户来源；
- V1 默认走 IAA-B4 自动挑选。

### 6.5 账户数据事实源

- 飞书账户表（iaa/iap/测试户）是账户唯一业务事实源；Dashboard 不维护第二套账户基础数据；
- SQLite 只保存：飞书账户缓存、最后同步时间、分配意图、分配执行结果、同日 CID 占用、PlanSpec 账户快照、异常和对账记录；
- 分配前必须重新读取飞书最新数据；飞书与 SQLite 不一致时，以飞书为当前实际状态，SQLite 只记录自动化历史。

## 7. 核心领域模型（SQLite）

```text
DramaTask          飞书剧目行对应的本地任务
QueueItem          活动队列项（状态、租约、心跳、重试次数）
WorkflowRun        一次任务执行的流程运行
StepRun            流程中每一步运行记录
TaskLedger         完成后的最小业务台账（长期保留）
PromotionLinkSet   每部剧的 IAA/9.9/2.9 链接集合及来源字段
DramaAsset         投放系统剧目资源（delivery_drama_id、album_id）
PlanSpec           标准投放计划规格（账户、CID、推广内容、产品库、命名）
AccountUsageRecord 账户 CID 使用记录（剧名、日期、角色、批次）
AccountSheetSnapshot 飞书账户数据缓存与最后同步时间
AccountAllocation    账户分配意图与执行结果（PENDING/WRITING/CONFIRMED/PARTIAL_WRITE/FAILED）
ExecutionEvent     执行日志事件
ExecutionArtifact  截图/文件产物
RuleSet/RuleVersion 动态规则及版本
ConfigSnapshot     任务执行时使用的配置快照
ConfigChangeLog    配置变更审计
```

关键幂等规则：

- 剧目行以 `sheet_row + drama_name` 去重；
- 链接以 `task_id + link_type + url_hash` 去重；
- 剧目资源以 `drama_name + album_id` 防重复创建；
- 创建类操作超时先对账，禁止直接重复提交。

## 8. 状态机

任务状态：

```text
WAITING_TIME → READY → QUEUED → RUNNING
                                    ├→ COMPLETED
                                    ├→ MANUAL_REVIEW
                                    └→ FAILED / CANCELLED
```

队列状态：

```text
WAITING_TIME / QUEUED / CLAIMED / RUNNING /
RETRY_WAIT / PAUSED / MANUAL_REVIEW / COMPLETED / CANCELLED
```

链接状态：

```text
NOT_STARTED / EXTRACTING / AVAILABLE / NOT_AVAILABLE /
SPECIAL_LENGTH / VALIDATED / DRAMA_MISMATCH / FAILED
```

## 9. 规则与配置中心

事实源（最终方案）：

- `configs/defaults/*.json`：系统默认配置和初始化模板，只读；
- SQLite：当前生效配置、规则版本、配置快照、变更审计；
- `configs/exports/*.json`：手动导出、备份、迁移、恢复；
- 首次启动：读取 defaults → 校验 → 导入 SQLite → 创建初始规则版本；之后运行时以 SQLite 为准；
- Dashboard 流程：编辑草稿 → 保存 SQLite → 校验 → 规则模拟 → 发布 → 生成 RuleVersion → 新任务读取已发布版本；运行中任务继续使用自己的 ConfigSnapshot。

首批规则（V1 建结构，值由用户后续维护）：

- IAA 选集阈值（默认 50：>50 选第 2 集，<=50 选第 1 集）；
- IAP 2.9：目标 2.9，区间 2.6—5.0；IAP 9.9：目标 9.9，区间 8.8—13.8；
- 同距离优先高价；距离相同按价格高、页面靠前排序；
- IAA 账户 B1/B4/B7/BX；IAP B1=9.9、B2=2.9；测试户 B4 或测试户表；
- 任务命名模板；轮询间隔/超时（默认 5 分钟 / 2 小时）、重试次数（默认 3）；
- CID 配置：CID、广告预设、抖音号、开户预设、主体、投放类型、生效时间、启用状态（具体值由用户在真实提交前录入）；
- 素材分组规则、标准计划固定字段（见第 11 节）；
- 测试户来源开关。

SQLite 稳定性配置：`journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`；数据库 `data/database/app.db`；Alembic 迁移；迁移/批量导入/高风险发布/手动清理前自动备份到 `data/backups/`。

## 10. 平台适配器

```text
FeishuAdapter        剧目表/账户表读写、N 状态读取、链接回填、M 写入
TomatoAdapter        番茄搜索/登录态/免费付费入口/链接提取（DOM 优先，剪贴板兜底）
DeliverySystemAdapter 剧目资源、推广内容配置、计划提交、任务状态轮询
OceanEngineAdapter   巨量产品库建产品（先 Mock，后真实）
```

- 每个平台先 Mock，再只读验证，再“填写但不提交”，最后单条/批次提交；
- 每个平台独立持久化浏览器 Session；
- 番茄域名可配置，默认 `changdunovel.com`，兼容 `changdupingtai.com`；
- 页面选择器：稳定选择器放 Page Object 代码，JSON 只放域名/页面路径/紧急覆盖选择器；优先级 role/label/text → data 属性 → CSS → XPath；
- OceanEngineAdapter V1 只负责巨量产品库，不负责标准计划状态判断；
- 任务完成状态以投放系统巨量引擎 V2 任务页为最终来源。

## 11. 关键业务规则摘要

- IAA 链接只能从番茄免费入口提取，本地禁止构造/拼接；
- IAP 模板扫描全部可见模板，按“档位1价格”分类；区间外忽略；
- 无匹配 IAP 模板属正常业务结果，不整剧失败；
- 链接长度不等于 501 记为 `SPECIAL_LENGTH`，不判无效；
- 统一链接信息：task_id、drama_name、link_type、promotion_url、source_platform、source_entry、acquisition_method、source_column、url_length、link_status、acquired_at、rule_version；
- 番茄来源：`TOMATO / FREE|PAID / PAGE_EXTRACTION`；剧变来源：`JUBIAN / FEISHU_SHEET / DIRECT_READ / J|K|L`；剧变读到的空值表示该类型链接不存在，不构造链接；
- 任意有效链接（IAA/2.9/9.9）都可获取专辑 ID，默认顺序 IAA → 2.9 → 9.9；
- 推广内容配置只创建缺失项；`iaa-平台-剧名` / `9.9-平台-剧名` / `2.9-平台-剧名`；
- 固定字段：主剧=当前剧目、分销商=微智造、推广链接=对应类型链接；
- 链接与主剧不匹配：停止、截图、`MANUAL_REVIEW`，禁止自动换主剧/换剧名；
- 命名模板（原样复制）：
  - 端付：`<平台方>#端付<剧名称><日期>ubr-<创建日期>-<时分秒-n>`
  - 端免：`<平台方>#端免<剧名称><日期>bxr-<创建日期>-<时分秒-n>`
  - 测试：`<平台方>#测试<剧名称><日期>cbo-<创建日期>-<时分秒-n>`
  - 漫剧全域：`<平台方>#漫剧全域<剧名称><日期>bxr-<创建日期>-<时分秒-n>`（V1 预留）
- 标准计划固定字段：创编方式=极速创建、投放方式=标准投放、推广业务=端原生；项目规则=按广告数生成、广告规则=按素材组生成、素材组平均分配=关闭、标题组平均分配=关闭；
- 素材选择通铺：清空原有素材 → 搜索精确剧名 → 300 条/页 → 全选当前页 → 完成；校验已选素材数=剧目有效素材总数，不一致停止提交；
- 常规素材分组：N<=30 → 1 组复制 2 次 = 3 组；30<N<=60 → 每组 ceil(N/2)、2 组各复制 2 次 = 6 组；60<N<=90 → 每组 ceil(N/3)、3 组各复制 1 次 = 6 组；N>90 → 均匀分配、每组<=30、组数=不小于 ceil(N/30) 的最小 3 的倍数；常规计划 `ad_limit_per_project=最终组数/3`、`expected_project_count=3`；
- 测试户素材分组：N<20 → 每组 2 条；N>=20 → 每组 3 条；不复制；`ad_limit=min(10,ceil(G/3))`、`project_count=ceil(G/ad_limit)`；
- 巨量产品库固定路径：杨硕总体户 → B组李伟层级 → 资产 → 商品管理 → 通用版 → lw全域ROI3产品库；字段：投放载体=端原生、专辑ID=当前 album_id、版权方=厦门骑驰网络科技有限公司、变现模式=付费变现+流量变现；
- RESULT_UNCERTAIN：任何创建操作超时或结果不明确 → 先查询外部平台 → 找到目标资源则补记成功 → 确认不存在才允许重试；禁止直接重复点击创建或提交。

## 12. 安全与运行约束

- `ALLOW_FINAL_SUBMIT=false` 默认；只有页面执行稳定后人工开启；
- Cookie/Session 存 `data/sessions/`，密钥走环境变量，不落代码和 Git；
- 日志不记录完整 Cookie/Token/密码；
- 删除操作先备份；本地数据定期可导出；
- 单 Worker；平台写操作串行；创建操作幂等；
- Dry Run 不污染飞书表；
- 迁移/批量导入/高风险配置发布/手动清理前自动备份数据库到 `data/backups/`；
- 飞书写入前重新读取目标行，非空剧名绝不覆盖；部分写入标记 `PARTIAL_WRITE` 并进人工。

## 13. 测试计划

单元测试：

- 链接选集边界（50/51）；
- IAP 模板区间与排序（距离、价格、页面顺序）；
- 链接状态流转、长度处理；
- 队列领取/租约/心跳/崩溃恢复；
- 账户同日复用限制、测试户挑选；
- 账户完整块分配（10 行/6 行校验、空位扫描、追加块、部分写入回滚）；
- 命名模板渲染；
- 规则版本与配置快照；
- PlanSpec 校验（CID 映射、模板匹配、命名）。
- 素材选择与常规/测试户素材分组计算；
- 配置事实源（defaults 初始化 → SQLite 生效 → exports 备份）。

集成测试：

- Mock 全链路 Dry Run：飞书读表 → 链接提取 Mock → 投放系统 Mock → 产品库 Mock → PlanSpec → 状态轮询 Mock → M 写入（仅真实模式）；
- 失败/重试/超时/MANUAL_REVIEW 场景；
- 飞书表真实回读校验（只读/回写后回读）。

浏览器测试（后续阶段）：

- 番茄免费/付费入口只读验证 → 填写不提交 → 单条提交；
- 投放系统剧目资源、推广配置、计划提交、状态轮询；
- 巨量产品库建产品。

## 14. 验收标准

- 可持久化任务、自动入队出队、崩溃恢复；
- 可释放运行资源、清理过期日志；
- 可生成/发布规则版本与配置快照；
- 可完整跑 Mock Dry Run，不访问真实平台；
- 可在不提交真实计划时生成 PlanSpec；
- Dashboard 可查询任务、队列、异常、规则、链接来源与流转；
- 真实模式：计划状态 `已完成` 才写 M=1，飞书 N 自动变 OK；
- 平台 Adapter 可独立替换。

## 15. 已确认决策记录

- 两处现有仓库（`short drrama Analysis`、`short-drama-monitor`）作为资产来源，Adapter 包装复用，不改原仓库；
- 番茄=畅读/番茄资源，域名可配置；投放系统=`web.tjhaozew.top/juliangg/v2`；巨量=`business.oceanengine.com`；
- 本地 Web 工作台，V1 浏览器应用模式，后期再套桌面壳；
- 登录态=手动登录 + 持久化 Session；
- 任务源=飞书 Sheet + Bitable 思路落为 Sheet；E 列=投放时间；
- 回填=J/K/L 链接 + M=1；失败原因本地存储；
- 轮询 5 分钟/最长 2 小时；失败重试 3 次；
- 无飞书 IM 推送；Dashboard 无登录；
- 配置事实源=SQLite，defaults JSON 只读初始化，exports JSON 备份迁移；
- 账户整块分配：IAA 10 行 / IAP 6 行，块序 `3+3+3+1` 与 `3+3` 写死，实际账户数据和行号实时读飞书；
- 同一 CID 当天不重复分配；老块保留，追加新块；
- 测试户来源默认 IAA-B4 自动挑选，后续可切测试户表。
- 每天 00:00 全量扫描 + 应用启动即时扫描 + 每小时增量扫描。

## 16. 待补充/开放项

- 投放系统/巨量页面选择器与字段（开发时 Playwright 探测）；
- CID → 广告预设/抖音号/开户预设/主体/投放类型/生效时间的具体值（Dashboard 后续录入）；
- 测试户账户表具体内容；
- 账户表是否新增显式 `账户组` 列（实现时按块顺序识别或补列）；
- Git 仓库初始化与远程连接确认（本地仓库，提交前向用户确认，Commit Message 中文，推送用 git bash）。

## 17. 关联子计划

- 前端 UI 独立子计划：[docs/plans/frontend-ui-development-plan.md](../../plans/frontend-ui-development-plan.md)
