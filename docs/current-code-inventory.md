# 现有代码资产清单

> 生成时间：2026-08-06
> 用途：Phase 0 资产盘点，为短剧投放全流程自动化工作台（新系统）的 Adapter 包装复用提供依据。
> 来源仓库（只读，不修改）：`D:\work\short drrama Analysis`、`D:\work\聚赢\short-drama-monitor`
> 复用分类：`可直接包装复用` 指逻辑/选择器/接口可直接作为新系统 Adapter 实现基础；`仅页面/结构参考` 指保留页面结构、选择器、业务流程线索，但整体逻辑与业务耦合过深，需按新系统边界重写。

## 一、short drrama Analysis（番茄/畅读爬虫与分析）

### 1.1 核心爬虫与 Adapter

| 脚本路径 | 作用 | 新系统映射 | 复用分类 |
|---|---|---|---|
| `drama_priority/crawlers/fanqie.py` | `FanqieCrawlerClient`：Playwright 登录态（storage_state）+ 搜索剧目 + 查发布状态 + 批量爬取，输出 JSONL/发布记录 | `TomatoAdapter` 登录态管理与剧目状态查询 | 可直接包装复用 |
| `drama_priority/adapters/fanqie_bridge.py` | `FanqiePublishDramaSourceAdapter`：把爬虫结果规范化为 `PublishDramaRecord`，实现 `fetch_by_date_range` / `fetch_incremental` / `health_check` | `TomatoAdapter` 数据规范化层（发布记录协议可直接沿用） | 可直接包装复用 |
| `drama_priority/adapters/base.py` | `PublishDramaSourceAdapter` / `RankingDramaSourceAdapter` 协议定义 | 新系统 Adapter 接口设计参考 | 仅页面/结构参考 |
| `drama_priority/adapters/external.py` | 外部数据源 Adapter 占位：配置校验、未实现阻断、健康检查 | 新系统真实 Adapter 接入边界参考 | 仅页面/结构参考 |
| `scripts/fanqie_batch_crawl.py` | 批量爬取 CLI：读取剧目名单 → `FanqieCrawlerClient` 批量查发布状态 → 输出 JSONL + 发布 JSON | `TomatoAdapter` 批量任务入口参考 | 可直接包装复用 |

### 1.2 FastAPI 分析与前端

| 脚本路径 | 作用 | 新系统映射 | 复用分类 |
|---|---|---|---|
| `drama_priority/api.py` | FastAPI 只读查询 API（日优先级、剧目、榜单、账户、数据质量等），静态托管 frontend | 新系统 Dashboard 后端 API 页面结构参考 | 仅页面/结构参考 |
| `drama_priority/server.py` | `uvicorn` 启动入口，SQLite 初始化 | 新系统 FastAPI 启动模式参考 | 仅页面/结构参考 |
| `drama_priority/models.py` | `AdapterHealth`、`PublishDramaRecord`、`RankingDramaRecord` 等领域模型 | 新系统番茄数据模型字段参考 | 可直接包装复用 |
| `drama_priority/normalizers.py` | 剧名、发布时间等规范化函数（含上海时区） | `TomatoAdapter` 数据规范化复用 | 可直接包装复用 |
| `frontend/index.html` + `frontend/src/*.mjs` | 原生 JS 分析看板（API 客户端、视图模型、样式） | 新系统 Vue Dashboard 页面/交互结构参考 | 仅页面/结构参考 |
| `tests/test_fanqie_bridge_adapter.py` | 桥接 Adapter 测试 | Adapter 包装后的回归测试参考 | 可直接包装复用 |
| `tests/test_fanqie_batch_crawler.py` | 批量爬虫测试 | 爬虫复用测试参考 | 可直接包装复用 |

## 二、聚赢/short-drama-monitor（飞书/投放/巨量监控）

### 2.1 畅读/番茄登录与爬虫

| 脚本路径 | 作用 | 新系统映射 | 复用分类 |
|---|---|---|---|
| `tasks/01-iam-2359/changdu_crawler.py` | 畅读/番茄后台发布状态查询：登录态恢复、漫剧列表导航、发布状态解析、缓存、`check_drama_status` / `bulk_check` | `TomatoAdapter` 登录 Session 恢复、列表页选择器、发布状态查询核心实现 | 可直接包装复用 |
| `tasks/01-iam-2359/refresh_changdu_cookie.py` | 手动/定时刷新畅读 Cookie（headless 遇验证码时 `--headed`） | `TomatoAdapter` Session 刷新与验证码人工介入流程 | 可直接包装复用 |
| `tasks/00-crawler/changdu_crawler.py` | 畅读短剧爬虫 v1：Playwright 登录 + requests 会话 + 全量剧目列表爬取 | 番茄 Session 复用方式参考（含 API 捕获思路） | 仅页面/结构参考 |
| `tasks/00-crawler/changdu_crawler_v2.py` | 畅读短剧爬虫 v2：手动验证码处理 + Cookie 校验 | 登录/验证码流程参考 | 仅页面/结构参考 |
| `tasks/00-crawler/crawler_v3.py` | 畅读短剧爬虫 v3：应用切换 + 剧目列表爬取 | 番茄应用切换选择器参考 | 仅页面/结构参考 |
| `tasks/00-crawler/crawler_switch_app.py` | 四类应用切换探索脚本 | 番茄应用切换页面结构参考 | 仅页面/结构参考 |
| `test_changdu.py` / `test_login.py` / `test_login9.py` / `test_pw_login.py` / `test_pw2.py` / `test_pw3.py` | 畅读登录、billing 页、Cookie 复用等探索测试 | 登录选择器与页面行为参考 | 仅页面/结构参考 |
| `tasks/01-iam-2359/test_fanqie_722.py` / `test_fanqie_publish.py` | 指定日期番茄发布状态批量验证脚本 | 批量验证流程参考 | 仅页面/结构参考 |
| `tasks/01-iam-2359/fanqie_smoke_test.py` | Cookie + 漫剧列表 + 发布状态冒烟测试 | 登录态健康检查参考 | 可直接包装复用 |

### 2.2 投放系统与巨量页面监控

| 脚本路径 | 作用 | 新系统映射 | 复用分类 |
|---|---|---|---|
| `tasks/01-iam-2359/fanqie_batch_verify.py` | 按日期批量验证番茄发布状态，结果私发负责人（读飞书表、判定可投放/不可投放） | 番茄发布状态批量验证 + 飞书回填流程参考 | 可直接包装复用（含隐式飞书依赖，包装时需先解耦） |
| `tasks/08-partial-failed/partial_failed_monitor.py` | 投放系统巨量引擎 V2 任务页「部分失败」监控：抓取任务、6 类不重试规则、自动重试、飞书推送去重 | `DeliverySystemAdapter` 任务列表/详情/重试页面选择器与状态轮询核心参考 | 可直接包装复用 |
| `tasks/06-tjhaozew-monitor/tjhaozew_monitor.js` | 巨量引擎全局看板高速消耗低回收监控：报表阈值、分时 ROI、防刷屏推送 | 巨量报表页面结构参考；新系统 V1 不吸收监控，仅保留页面线索 | 仅页面/结构参考 |
| `tasks/07-tjhaozew-watchdog/tjhaozew_watchdog.py` | 巨量监控 watchdog：日志间隔、sandbox、网络健康检查与告警 | 新系统监控健康检查设计参考 | 仅页面/结构参考 |
| `shared/scripts/circuit_breaker.py` | 飞书 @ 消息熔断器 | 新系统推送/风控参考 | 可直接包装复用 |
| `shared/scripts/confirm.py` / `cron_audit.py` / `iam_cron_watchdog.py` | 推送确认、cron 审计、IAM cron watchdog | 新系统运维/审计机制参考 | 仅页面/结构参考 |
| `server_api.py` | 面板 API：各定时任务触发、日志与运行状态查询 | 新系统任务调度 API 页面结构参考 | 仅页面/结构参考 |

### 2.3 飞书提醒任务（V1 不吸收，仅记录）

| 脚本路径 | 作用 | 新系统映射 | 复用分类 |
|---|---|---|---|
| `tasks/01-iam-2359/iam_check.py` | IAA 剧目巡查：读飞书表、J 列分类、番茄发布状态交叉验证、提醒控制 | 飞书表读取与番茄状态交叉验证流程参考 | 仅页面/结构参考 |
| `tasks/02-kanju-before-1240/r3_t0_d_reminder.py` | 看剧提醒（12:40 前） | V1 暂不做 IM 推送，仅业务规则参考 | 仅页面/结构参考 |
| `tasks/03-kanju-after-1240/r3_t0_d_reminder.py` | 看剧催办（12:40 后） | V1 暂不做 IM 推送，仅业务规则参考 | 仅页面/结构参考 |
| `tasks/04-r3-t1-reminder/r3_t1_reminder.py` | r3 整点推送（t-1 R3 未上） | V1 暂不做 IM 推送，仅业务规则参考 | 仅页面/结构参考 |
| `tasks/05-r3-check/r3_check.py` | 标黄/标红检查（飞书样式读取、J 列映射） | 飞书 Sheet 样式读取与状态映射参考 | 仅页面/结构参考 |
| `tasks/09-bangdan-relay/bangdan_relay_v2_t1_window.py` | 热力榜上榜转发（已暂停） | V1 不吸收，仅页面结构参考 | 仅页面/结构参考 |

## 三、Adapter 映射汇总

| 新系统 Adapter | 可包装资产 |
|---|---|
| `TomatoAdapter` | `FanqieCrawlerClient`、`fanqie_bridge.py`、`changdu_crawler.py`、`refresh_changdu_cookie.py`、`fanqie_batch_verify.py` |
| `DeliverySystemAdapter` | `partial_failed_monitor.py`（任务列表/详情/重试页面与选择器） |
| `OceanEngineAdapter` | `tjhaozew_monitor.js`（巨量报表页面结构，仅参考） |
| `FeishuAdapter` | `iam_check.py` / `r3_check.py` 的飞书 Sheet 读取与样式解析思路（仅参考） |

## 四、路径验证结果

| 资产路径 | Test-Path |
|---|---|
| `D:\work\short drrama Analysis\drama_priority\crawlers\fanqie.py` | 通过 |
| `D:\work\short drrama Analysis\drama_priority\adapters\fanqie_bridge.py` | 通过 |
| `D:\work\short drrama Analysis\drama_priority\adapters\base.py` | 通过 |
| `D:\work\short drrama Analysis\drama_priority\adapters\external.py` | 通过 |
| `D:\work\short drrama Analysis\scripts\fanqie_batch_crawl.py` | 通过 |
| `D:\work\short drrama Analysis\drama_priority\api.py` | 通过 |
| `D:\work\short drrama Analysis\drama_priority\server.py` | 通过 |
| `D:\work\short drrama Analysis\drama_priority\models.py` | 通过 |
| `D:\work\short drrama Analysis\drama_priority\normalizers.py` | 通过 |
| `D:\work\short drrama Analysis\frontend\index.html` | 通过 |
| `D:\work\short drrama Analysis\frontend\src\api.mjs` | 通过 |
| `D:\work\short drrama Analysis\frontend\src\app.mjs` | 通过 |
| `D:\work\short drrama Analysis\frontend\src\view-model.mjs` | 通过 |
| `D:\work\short drrama Analysis\frontend\src\styles.css` | 通过 |
| `D:\work\short drrama Analysis\tests\test_fanqie_bridge_adapter.py` | 通过 |
| `D:\work\short drrama Analysis\tests\test_fanqie_batch_crawler.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\01-iam-2359\changdu_crawler.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\01-iam-2359\refresh_changdu_cookie.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\00-crawler\changdu_crawler.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\00-crawler\changdu_crawler_v2.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\00-crawler\crawler_v3.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\00-crawler\crawler_switch_app.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\test_changdu.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\test_login.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\test_login9.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\test_pw_login.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\test_pw2.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\test_pw3.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\01-iam-2359\test_fanqie_722.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\01-iam-2359\test_fanqie_publish.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\01-iam-2359\fanqie_smoke_test.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\01-iam-2359\fanqie_batch_verify.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\08-partial-failed\partial_failed_monitor.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\06-tjhaozew-monitor\tjhaozew_monitor.js` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\07-tjhaozew-watchdog\tjhaozew_watchdog.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\shared\scripts\circuit_breaker.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\shared\scripts\confirm.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\shared\scripts\cron_audit.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\shared\scripts\iam_cron_watchdog.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\server_api.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\01-iam-2359\iam_check.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\02-kanju-before-1240\r3_t0_d_reminder.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\03-kanju-after-1240\r3_t0_d_reminder.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\04-r3-t1-reminder\r3_t1_reminder.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\05-r3-check\r3_check.py` | 通过 |
| `D:\work\聚赢\short-drama-monitor\tasks\09-bangdan-relay\bangdan_relay_v2_t1_window.py` | 通过 |

结论：清单内 46 个路径全部存在；在缺少针对原脚本的新系统回归测试前，不推翻任何现有脚本，统一按「Adapter 包装复用」处理。
