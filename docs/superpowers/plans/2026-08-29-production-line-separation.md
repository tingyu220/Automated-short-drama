# 产线分离：端原生漫剧与微信小程序独立运行

## 背景

当前系统只有一条产线（端原生漫剧），链接搭建在番茄后台完成，随后经过投放系统创建剧目资源和推广配置。
后续需要新增微信小程序产线，链接搭建在 youxuan2 平台（`http://duanju.youxuan2.cn/video/info`）完成，
不需要投放系统，但需要在巨量引擎中搭建多项内容。

两条产线的搭建流程完全不同，需要从数据模型、服务编排、适配器层到前端面板全面隔离。

## 目标

搭建最小可用框架，使两条产线在架构层面完全隔离：
1. 任务数据模型可区分产线（`end_type` 字段）
2. 服务编排按 `end_type` 分流到不同流程
3. 新增 YouxuanAdapter 协议（桩），后续填充实际操作
4. 端原生产线现有流程不受影响

## 产线对比

| 维度 | 端原生漫剧 (NATIVE) | 微信小程序 (MINIPROGRAM) |
|------|---------------------|--------------------------|
| 链接搭建平台 | 番茄后台 | youxuan2.cn |
| 投放系统 | 需要（剧目+推广配置） | 不需要 |
| 巨量引擎 | 创建产品 | 需要搭建多项内容（TBD） |
| 链接类型 | IAA / 2.9 / 9.9 | TBD |
| 任务来源 | 飞书表导入 | 飞书表导入 / 直接输入剧目名 |

## 架构设计

### 1. 数据模型

```
DramaTask
  + end_type: str = "NATIVE"   # NATIVE / MINIPROGRAM
```

- `source_key` 纳入 `end_type`，使同一剧目在不同产线可以独立存在
- 数据库迁移：`drama_task` 表增加 `end_type` 列，默认 `NATIVE`

### 2. 适配器层

新增 `YouxuanAdapter` 协议（桩接口）：

```python
class YouxuanAdapter(Protocol):
    def extract_links(self, drama_name: str) -> list[PromotionLink]: ...
```

- 协议方法后续根据 youxuan2 平台实际操作扩展
- Mock 实现：返回确定性链接
- `AdapterBundle` 增加 `youxuan` 字段

### 3. 服务编排

#### LinkReadinessService

按 `end_type` 分流：

```
NATIVE:
  LINK_EXTRACTION (番茄) → DELIVERY_DRAMA → PROMOTION_CONFIG → LINK_READY

MINIPROGRAM:
  LINK_EXTRACTION (youxuan2) → LINK_READY
  (巨量引擎操作 TBD，后续插入新阶段)
```

#### TaskPreparationService

按 `end_type` 分流链接解析：

```
NATIVE + TOMATO:  番茄 Adapter 提取 IAA/IAP
NATIVE + JUBIAN:   表内链接
MINIPROGRAM:       youxuan2 Adapter 提取链接（桩）
```

### 4. API / 前端

- `TaskSummary` / `TaskDetail` 增加 `end_type` 字段
- 任务列表 API 支持 `end_type` 筛选
- 前端任务列表显示产线标识
- 后续前端面板物理分离

### 5. 配置

- `Settings` 增加 `youxuan_base_url`
- `configs/defaults/youxuan_selectors.json`（桩文件）

## 实施步骤

1. 创建 EndType 常量 + 更新 DramaTask
2. 数据库迁移
3. ORM 模型 + 仓储层适配
4. source_key 纳入 end_type
5. YouxuanAdapter 协议 + Mock 实现
6. AdapterBundle 更新
7. LinkReadinessService 分流
8. TaskPreparationService 分流
9. API Schema + 路由
10. 前端类型
11. 测试

## 不在本次范围

- youxuan2 平台页面对象和真实 Adapter（后续提供操作步骤后实现）
- 巨量引擎小程序产线操作（后续提供截图后实现）
- 前端面板物理分离（后续独立任务）
- 飞书表导入时区分产线的列映射（后续根据飞书表结构调整）
