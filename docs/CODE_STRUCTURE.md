# Prophet 代码结构

## 总体调用关系

```text
desktop.py
  └─ pywebview 加载 web/
       └─ web/app.js 调度 web/modules/ 并调用 app_api.py
            ├─ app_api.py：组合 api/ 中的公开桥接方法
            │    ├─ api/settings.py：设置、健康检查和数据库路径
            │    ├─ api/profile.py → person_profile/：人物画像页面
            │    ├─ api/chat.py → chat_export.py / chat_analysis.py：聊天页面
            │    ├─ api/fortune.py → fortune_app.py → fortune/：算命页面
            │    └─ api/dialogs.py：原生文件对话框
            └─ background_jobs.py：统一执行耗时任务
```

界面只通过 `app_api.py` 访问 Python。桥接层负责输入校验、错误信封和任务状态；业务模块负责实际处理。需要启动本机脚本时统一通过 `process_runner.py`。

## 根目录代码

| 文件 | 功能 |
|---|---|
| `desktop.py` | 桌面程序入口；确定源码/打包资源路径、用户数据目录、系统主题，创建 pywebview 窗口，并提供打包自检。 |
| `app_api.py` | 组合并暴露稳定的 `AppApi`，保留桥接自检入口。 |
| `background_jobs.py` | 全局双线程任务池，避免模型与导出任务阻塞界面。 |
| `process_runner.py` | 可取消、可超时的本机子进程执行器。 |
| `chat_export.py` | 校验聊天导出参数并调用 QQ/微信导出脚本。 |
| `chat_analysis.py` | 聊天文件检查、任务路径、Agent 提示词和一键分析调用。 |
| `fortune_app.py` | 七种术式的应用服务；整理输入、调用引擎、保存记录和导出报告。 |
| `analysis.py` | 兼容旧导入的薄封装，实际实现位于 `person_profile/analysis.py`。 |
| `storage.py` | 兼容旧导入的薄封装，实际实现位于 `person_profile/storage.py`。 |
| `parsers.py` | 兼容旧导入的薄封装，实际实现位于 `person_profile/parsers.py`。 |
| `profile_export.py` | 兼容旧导入的薄封装，实际实现位于 `person_profile/export.py`。 |
| `test_core.py` | 人物画像、解析、存储、桥接、导入导出等核心回归检查。 |
| `test_fortune.py` | 术式引擎的固定样例一致性检查。 |

## API 桥接层

| 文件 | 功能 |
|---|---|
| `api/base.py` | `ApiBase`；应用路径、环境配置读取、输入校验、数据库定位、任务提交与状态查询。 |
| `api/settings.py` | 设置读取/保存、健康检查、数据库目录迁移。 |
| `api/profile.py` | 人物、材料、画像版本、预测、复盘、导入和导出。 |
| `api/chat.py` | 聊天导出、聊天文件检查、Agent 提示词、手动命令和一键分析。 |
| `api/fortune.py` | 起盘、解读、术数档案、预测复盘和数据库维护。 |
| `api/dialogs.py` | pywebview 原生文件和文件夹选择框。 |

新增页面接口时，优先在对应的 `api/*.py` 中增加方法；不要把页面业务重新塞回 `app_api.py`。公开方法名是前端契约，修改前要同步检查 `web/app.js` 的调用。

## 人物画像核心

| 文件 | 功能 |
|---|---|
| `person_profile/analysis.py` | 模型配置读取、标准库 HTTP 调用、结构化结果校验、材料分析、画像增量更新、预测和复盘。 |
| `person_profile/storage.py` | 人物、材料、画像版本、预测和复盘的 SQLite 数据层。 |
| `person_profile/parsers.py` | TXT、Markdown、CSV、JSON、PDF、DOCX、XLSX 的文本解析与大小限制。 |
| `person_profile/export.py` | 将人物画像、证据时间线和预测记录导出为 Markdown。 |

`person_profile/` 不依赖 pywebview 或网页对象。数据库路径由 `api/base.py` 决定，核心模块只接收明确的路径和参数。

## 前端

| 文件 | 功能 |
|---|---|
| `web/index.html` | 桌面壳、导航、设置弹窗和首屏启动动画结构。 |
| `web/styles.css` | 样式入口，只导入 `web/styles/` 下的分层样式。 |
| `web/styles/base.css` | 全局变量、基础布局、通用控件和响应式基础。 |
| `web/styles/profile.css` | 人物画像页面样式。 |
| `web/styles/chat.css` | 聊天导出、聊天分析、任务进度动画和对应响应式样式。 |
| `web/styles/fortune.css` | 赛博算命页面样式。 |
| `web/styles/overrides.css` | 主题覆盖和跨页面视觉统一规则。 |
| `web/styles/design-system.css` | 按 `docs/DESIGN-webflow.md` 落地的字体、色彩、控件、卡片、响应式和动效规则。 |
| `web/modules/core.js` | 路由、共享状态、DOM/API 工具、文本转义和通用标签。 |
| `web/modules/profile.js` | 人物画像页面渲染、表单和任务操作。 |
| `web/modules/chat.js` | 聊天导出与聊天分析页面渲染和任务操作。 |
| `web/modules/fortune.js` | 赛博算命页面渲染、起盘、解读和数据库备份、替换操作。 |
| `web/modules/common.js` | 设置、通知、桥接连接和原生目录选择。 |
| `web/app.js` | 前端启动、路由渲染调度、事件分发和错误兜底。 |

前端模块通过 `window.ProphetApp` 协作，调用统一使用 `window.pywebview.api`，并处理 `{ok: true, data}` / `{ok: false, error}` 两种结果。渲染用户或模型文本时必须经过现有的 HTML 转义函数。

## 受保护目录

以下目录本次重构不修改，继续保持各自的独立边界：

| 目录 | 性质 |
|---|---|
| `person_profile/` | 人物画像核心实现；默认保护，除非明确要求人物画像功能修改，否则不随意重构。 |
| `fortune/` | 纯 Python 术式引擎、日历换算、规则检索、独立存储、语料和 Schema。 |
| `exporters/` | Windows QQ/微信数据识别、解密和导出实现。 |
| `chat-material-extractor/` | 聊天规范化、分块、分期、模型调用和报告构建工具，含脚本、提示词、参考格式和独立说明。 |

这些目录内包含数据、Schema、提示词或说明文件，其中一部分不是运行时代码，但仍作为对应功能的核心资源保留；如需清理，应另行确认范围。

## 构建与配置

| 文件 | 功能 |
|---|---|
| `Prophet.spec` | PyInstaller 收集规则、动态模块、资源和排除项。 |
| `build_windows.ps1` | 清理构建缓存、生成 `dist-native/Prophet` 并运行打包自检。 |
| `requirements.txt` | 正式运行依赖；当前原生桌面版不依赖 Streamlit。 |
| `.env.example` | 模型、数据库、输出目录和限制参数模板。 |
| `assets/` | Windows 图标、明暗主题页面图标、可编辑 SVG 源和许可证。 |

## 文档与数据目录

| 目录/文件 | 性质 |
|---|---|
| `docs/` | 当前设计、设计参考和本结构说明。 |
| `tests/fortune_fixtures/` | 术式参考结果；其中一部分直接用于自动检查，其余保留作交叉验证。 |
| `data/` | 源码运行时数据库，不是代码。 |
| `output/` | 用户导出结果，不是代码。 |
| `.chat-material-work/` | 可继续执行的聊天分析阶段数据，不是缓存。 |
| `.venv/` | 本地 Python 环境。 |
| `build/`、`__pycache__/` | 可随时重建的临时文件。 |
| `dist-native/` | 当前原生桌面包。 |
