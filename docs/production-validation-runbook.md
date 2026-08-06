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

- 环境变量 `ALLOW_FINAL_SUBMIT=true`；
- CLI 追加 `--real`；
- 真实 Adapter 已配置（Settings 指向真实投放/巨量/飞书环境）；
- CLI 已支持 `--real` 与报告落盘，但完整真实链路需 Task 9.1 Playwright page 补齐后另行验收。

```powershell
$env:ALLOW_FINAL_SUBMIT = "true"
python -m backend.interfaces.cli.production_validation --real --ladder single --plan-type test
```

## 报告与失败处理

- 报告位置：`data/production-validation/<ladder>-<plan_type>-latest.md`；
- 报告包含步骤表格、汇总行与总体 PASS/FAIL；
- 失败时按报告表格定位失败步骤，再到异常中心/台账核对明细；单级失败不阻断后续阶梯；
- 修复后重跑对应 ladder 覆盖报告；
- 每个范围验证完成后保留台账与异常记录，用于后续回溯。
