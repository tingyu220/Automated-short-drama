# 一键启动脚本

## 开发模式

```powershell
.\scripts\start.ps1
```

默认启动 `MOCK` Worker；需要真实模式时明确传参：

```powershell
.\scripts\start.ps1 -WorkerMode REAL
```

或双击：

```
scripts\start.bat
```

- **Control Server**: http://127.0.0.1:8765
- **Vite 前端**: http://127.0.0.1:5173
- **Worker**: 后台运行，每 15s 心跳；真实执行浏览器默认隐藏
- 自动等待 healthz 就绪后 Chrome 应用模式打开 http://127.0.0.1:5173

## 正式模式

```powershell
.\scripts\start-workbench.ps1
```

正式模式同样支持 `-WorkerMode MOCK` 或 `-WorkerMode REAL`。

- 先执行 `npm run build` 构建 `dashboard/dist`
- 启动 Control Server（托管前端静态资源，端口 8765）+ Worker
- 自动等待 healthz 就绪后 Chrome 应用模式打开 http://127.0.0.1:8765

## 端口说明

| 模式 | API / 前端 | Vite |
|------|------------|------|
| 开发 | 8765 | 5173 |
| 正式 | 8765（托管前端） | - |

## 停止

所有模式下按 `Ctrl+C` 即可优雅停止所有子进程。

## Worker 单独启动

```powershell
cd backend
python -m backend.bootstrap.automation_worker --mode-check-interval 1
```

Worker 的目标模式在 Dashboard 顶部的“Worker运行模式”切换；切换后通常 1 秒内开始生效，真实模式还会额外等待浏览器启动。
登录时由“登录投放系统”单独打开可见浏览器；不要手动关闭登录流程中的窗口，完成登录后可关闭。
