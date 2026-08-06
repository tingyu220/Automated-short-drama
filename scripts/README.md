# 一键启动脚本

## 开发模式

```powershell
.\scripts\start.ps1
```

或双击：

```
scripts\start.bat
```

- **Control Server**: http://127.0.0.1:8765
- **Vite 前端**: http://127.0.0.1:5173
- **Worker**: 后台运行，每 15s 心跳
- 自动等待 healthz 就绪后 Chrome 应用模式打开 http://127.0.0.1:5173

## 正式模式

```powershell
.\scripts\start-workbench.ps1
```

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
*** End of File
