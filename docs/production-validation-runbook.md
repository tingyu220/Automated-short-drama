# 生产验证 Runbook

## 验证顺序

按以下顺序逐步扩大范围，每步通过后再执行下一步：

1. 单部测试户：`single / test`
2. 单部端免：`single / free`
3. 单部端付仅 9.9：`single / paid_9_9`
4. 单部端付仅 2.9：`single / paid_2_9`
5. 单部端付双模板：`single / both`
6. 3 部剧：`three / test`
7. 5 部剧：`five / test`
8. 10 部剧：`ten / test`

## Mock 模式

在 `backend` 目录执行：

```powershell
python -m backend.interfaces.cli.production_validation --ladder single --plan-type test
```

每次执行后自动生成 Markdown 报告，覆盖写入
`data/production-validation/<ladder>-<plan_type>-latest.md`；
stdout JSON 中的 `report_path` 指向该文件的绝对路径。

## 真实模式

真实模式前置条件：

- 环境变量 `WORKBUDDY_ALLOW_FINAL_SUBMIT=true`（即 Settings.allow_final_submit=true）；
- CLI 追加 `--real`；
- 真实 Adapter 已配置（Settings 指向真实投放/巨量/飞书环境）；
- 已运行 `scripts/extract-delivery-config.py`，并在 Dashboard 校验每个候选 CID 的主体、抖音号、广告预设和开户预设；生产 Worker 不生成任何占位配置；
- `data/extracted/delivery_task_resources.json` 已按剧名精确配置素材和 6 个标题包，示例：

```json
{
  "tasks": {
    "剧A": {
      "material_ids": ["素材ID-1", "素材ID-2"],
      "title_packages": ["标题包1", "标题包2", "标题包3", "标题包4", "标题包5", "标题包6"]
    }
  }
}
```

- `configs/defaults/*_selectors.json` 已依据当前真实页面 DOM 复核；缺选择器、剧目资源、CID 映射或主剧匹配时任务会在提交前进入人工处理；
- CLI 会自行启动 Playwright 页面并在结束后关闭；页面启动失败时输出结构化错误并退出 1。

```powershell
$env:WORKBUDDY_ALLOW_FINAL_SUBMIT = "true"
python -m backend.interfaces.cli.production_validation --real --ladder single --plan-type test
```

## 报告与失败处理

## 手动扫描兜底

Control Server 默认启动时扫描一次，此后每小时自动扫描。Dashboard 的“自动搭链接”页面提供“立即扫描”，用于在导入剧目后不等待整点：它只执行一次相同的调度扫描，返回新增、更新、入队和跳过数量，不会重复创建活动队列项。

导入表中的“待关联任务”表示导入记录已保存，但尚未按 `source_key` 关联本地任务；点击“立即扫描”后刷新页面即可确认关联结果。若仍未关联，检查调度器日志和来源键匹配。

- 报告位置：`data/production-validation/<ladder>-<plan_type>-latest.md`；
- 报告包含步骤表格、汇总行与总体 PASS/FAIL；
- 失败时按报告表格定位失败步骤，再到异常中心/台账核对明细；单级失败不阻断后续阶梯；
- 修复后重跑对应 ladder 覆盖报告；
- 每个范围验证完成后保留台账与异常记录，用于后续回溯。
