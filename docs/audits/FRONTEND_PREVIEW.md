# 前端本地预览的三种方式

> 背景：直接双击 `frontend/dist/index.html` 会白屏——Vite 构建产物内引用的是
> 绝对路径 `/assets/...`，且 React 单页应用必须经 HTTP 服务访问，`file://` 协议下
> 资源 404 / 模块加载被拦截，属正常现象，不是构建问题。

三种方式任选其一，均在 `D:\Desktop\asm` 下操作。

## 方式一：开发模式（日常推荐）

```powershell
cd D:\Desktop\asm\frontend
npm run dev
# 浏览器打开 http://127.0.0.1:6100/
```

- 启动成功标志：输出 `➜  Local:   http://127.0.0.1:6100/`
- 改源码自动热更新，适合边改边看。
- 6100 是项目刻意选定的端口（5173 段在本机端口排除范围内）。

## 方式二：预览构建产物

```powershell
cd D:\Desktop\asm\frontend
npm run preview
# 默认 http://127.0.0.1:6200（vite.config.ts 已把默认端口改出排除段）
```

- **本机注意**：Vite 原始默认 4173 落在 Windows 端口排除范围（4136–4235）内，会报
  `listen EACCES: permission denied`——这不是权限问题，是系统预留端口段。
  项目已在 `vite.config.ts` 把 preview 默认端口改为 **6200**（排除段之外），直接 `npm run preview` 即可。
- 如需临时换端口：
  ```powershell
  npx vite preview --port 6300
  ```
- 查询本机被排除的端口段：
  ```powershell
  netsh interface ipv4 show excludedportrange protocol=tcp
  ```

## 方式三：静态服务器托管 dist（验证构建产物时用）

```powershell
cd D:\Desktop\asm\frontend\dist
..\..\.venv\Scripts\python.exe -m http.server 8000
# 浏览器打开 http://127.0.0.1:8000
```

- 必须从 **`frontend\dist`**（含 index.html 和 assets\ 的目录）起服务。
- `.venv` 在该目录向上两级（`frontend\dist` → `frontend` → `asm`），路径别多跳一级。
- 换成任意静态服务器（如 `npx serve dist`）效果相同。

## 常见坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 双击 index.html 白屏 | file:// 协议无法加载绝对路径资源 | 用上面任一 HTTP 方式 |
| `listen EACCES` | 端口落在系统排除段（如 4173） | `--port` 换到排除段之外 |
| 页面变成 whl 文件下载列表 | 进错了 `D:\Desktop\asm\dist`（Python 后端打包目录） | 前端产物在 `frontend\dist` |
| `cd frontend\dist` 找不到路径 | 已在 `frontend` 内又写了一遍 `frontend` | 此时应 `cd dist` |
| `GET /favicon.ico 404` | 项目未配置 favicon | 无害，忽略 |

打开后看到左侧墨蓝导航栏 + 顶部「演示数据」徽章即为正常。
