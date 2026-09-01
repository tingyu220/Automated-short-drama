# Link Architecture V2 基础层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有生产链接获取行为的前提下，引入 PromotionAsset、统一采集结果、验证与采集服务，并把旧番茄 DOM 链路隔离为 Provider。

**Architecture:** `TaskPreparationService` 只编排任务状态并调用 `LinkAcquisitionService`；后者通过 `PromotionProvider` 获取候选、验证并持久化 `PromotionAsset`，再输出兼容的链接快照。第一轮仅接入 `LegacyDomProvider`，继续复用现有 Tomato Adapter 和 Page Object，不实现 Network/API。

**Tech Stack:** Python 3.12、dataclasses、SQLAlchemy 2、Alembic、pytest、Playwright（仅复用现有实现）

**Spec:** 用户于 2026-08-31 批准的 Link Architecture V2 Phase 1–4 方案；兼容 `docs/superpowers/specs/2026-08-16-link-readiness-stage-design.md` 与 `docs/superpowers/specs/2026-08-19-tomato-match-confirmation-design.md`。

## Global Constraints

- 保留 `DramaTask.link_set`，它仍是后续流程消费的已验证快照。
- 保留现有 Tomato Adapter、Page Object 与生产链接获取行为。
- 本轮不实现 Network/API、Shadow Mode、Youxuan 或微小路径业务。
- 多候选不得自动取第一条；未验证资产不得冻结到 `link_set`。
- Domain 不依赖 SQLAlchemy、Playwright 或 FastAPI。
- 所有实现遵循 TDD；未经用户确认不提交 Git。

---

### Task 1: PromotionAsset 领域模型与验证器

**Files:**
- Create: `backend/src/backend/domain/assets/promotion_asset.py`
- Create: `backend/src/backend/domain/acquisition/acquisition_result.py`
- Create: `backend/src/backend/domain/acquisition/promotion_asset_validator.py`
- Test: `backend/tests/unit/test_promotion_asset.py`
- Test: `backend/tests/unit/test_promotion_asset_validator.py`

**Interfaces:**
- Produces: `PromotionAsset`、`AcquisitionResult`、`PromotionAssetValidator.validate(task, result) -> AcquisitionResult`。
- Validation: 仅唯一、身份匹配、类型匹配且 URL 合法的资产可进入 `selected`；模糊或多候选结果保持 `AMBIGUOUS/UNVERIFIED`。

- [ ] 写领域模型与验证规则的失败测试。
- [ ] 运行定向测试，确认因模块不存在而失败。
- [ ] 最小实现枚举常量、数据类与验证规则。
- [ ] 运行定向测试，确认通过。

### Task 2: PromotionAsset 持久化

**Files:**
- Create: `backend/alembic/versions/20260831_0019_promotion_assets.py`
- Create: `backend/src/backend/infrastructure/database/models/promotion_asset.py`
- Create: `backend/src/backend/infrastructure/database/repositories/promotion_asset_repository.py`
- Modify: `backend/src/backend/infrastructure/database/models/__init__.py`
- Modify: `backend/src/backend/infrastructure/database/repositories/__init__.py`
- Modify: `backend/src/backend/domain/ports/repositories.py`
- Test: `backend/tests/unit/test_promotion_asset_repository.py`
- Modify: `backend/tests/unit/test_migrations.py`

**Interfaces:**
- Produces: `PromotionAssetRepository.save`、`save_all`、`list_by_task`、`find_by_identity`、`find_validated_by_task`、`list_ambiguous`。
- Identity: 优先 `source_platform + external_drama_id + link_type + episode/template_id`，缺失外部标识时不猜测合并。

- [ ] 写仓储往返、查询与迁移失败测试。
- [ ] 运行定向测试，确认表/仓储不存在导致失败。
- [ ] 增加 `0019` 迁移、ORM 和仓储最小实现。
- [ ] 运行仓储与迁移测试，确认通过。

### Task 3: LegacyDomProvider

**Files:**
- Create: `backend/src/backend/domain/ports/promotion_provider.py`
- Create: `backend/src/backend/platforms/tomato/providers/legacy_dom_provider.py`
- Create: `backend/src/backend/platforms/tomato/providers/__init__.py`
- Test: `backend/tests/unit/test_legacy_dom_provider.py`

**Interfaces:**
- Produces: `PromotionProvider.acquire(task) -> AcquisitionResult`。
- Consumes: 现有 Tomato Adapter、价格规则和 `scan_iap()`；把现有 `PromotionLink` 转成 `PromotionAsset`，并保留诊断信息。

- [ ] 写 Provider 复用已有 IAA/IAP 行为、传递人工确认候选的失败测试。
- [ ] 运行定向测试，确认 Provider 不存在导致失败。
- [ ] 最小实现 Provider 包装层，不修改 Page Object 行为。
- [ ] 运行 Provider 与现有 Tomato 测试，确认通过。

### Task 4: LinkAcquisitionService 与准备流程接入

**Files:**
- Create: `backend/src/backend/application/services/link_acquisition_service.py`
- Modify: `backend/src/backend/application/services/task_preparation_service.py`
- Test: `backend/tests/unit/test_link_acquisition_service.py`
- Modify: `backend/tests/unit/test_task_preparation_service.py`

**Interfaces:**
- Produces: `LinkAcquisitionService.acquire(task) -> AcquisitionResult`。
- Behavior: 获取候选、验证、保存所有候选；仅把 `selected` 中已验证的资产转换为兼容 `ResolvedLinks`/`link_set`。
- Compatibility: `JUBIAN`、`MINIPROGRAM` 继续走现有路径；TOMATO/NATIVE 经新服务调用 Legacy Provider。

- [ ] 写服务编排、资产保存、快照冻结和失败状态的失败测试。
- [ ] 运行定向测试，确认服务/接入缺失导致失败。
- [ ] 最小实现服务，并通过可选依赖注入接入 `TaskPreparationService`。
- [ ] 运行准备流程、链接准备和 Worker 相关回归测试。

### Task 5: 文档与全量验证

**Files:**
- Modify: `docs/architecture/system-architecture.md`
- Modify: `docs/rules/business-rules.md`
- Modify: `docs/workflows/delivery-launch-flow.md`

- [ ] 更新资产事实源、Provider 顺序和兼容快照说明。
- [ ] 运行新增及受影响的后端测试。
- [ ] 运行完整后端测试。
- [ ] 运行 `git diff --check`、迁移检查和 `git status --short`。
- [ ] 输出变更清单与验证结果；等待用户确认后再提交。
