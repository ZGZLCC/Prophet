# Prophet 1.1.0

本机优先的桌面工作台，用于聊天记录导出、证据化人物画像、聊天分析，以及可复现的传统术数记录。

Prophet 由 `desktop.py` 启动 pywebview 窗口，直接加载本地 HTML、CSS 和 JavaScript，**不启动 Web 服务，也不占用端口**。聊天原文、画像证据、结构化盘面和复盘结果都先落盘到本机 SQLite，模型只负责生成解释性内容。

- 平台：Windows 10/11、macOS 11+（Apple Silicon）
- 技术栈：Python 3.11+ / 原生 HTML、CSS、JavaScript
- 许可：[MIT](LICENSE)

---

## 下载安装

普通使用不需要配置 Python 环境，直接下载打包好的免安装版：

**<https://github.com/ZGZLCC/Prophet/releases/latest>**

| 平台 | 下载 | 使用 |
|---|---|---|
| Windows | `Prophet-windows-x64.zip` | 解压后双击 `Prophet.exe` |
| macOS（Apple Silicon） | `Prophet-macos-arm64.zip` | 解压后把 `Prophet.app` 拖进"应用程序" |

压缩包旁附有 `.sha256`。Windows 可用 `Get-FileHash Prophet-windows-x64.zip -Algorithm SHA256` 核对，macOS 用 `shasum -a 256 Prophet-macos-arm64.zip`。

macOS 包未做代码签名，首次打开会被 Gatekeeper 拦下。解决办法是**右键点 `Prophet.app` → 打开**，或执行一次：

```bash
xattr -dr com.apple.quarantine /Applications/Prophet.app
```

首次启动会生成配置模板和两个数据库，之后所有用户数据都留在这个目录：

| 平台 | 数据目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\Prophet` |
| macOS | `~/Library/Application Support/Prophet` |

```text
Prophet/
├─ .env          # 模型配置、主题、时区、默认目录
├─ data\
│  ├─ sentiment.db   # 人物画像
│  └─ fortune.db     # 术式记录
└─ output\           # 默认导出目录
```

发布包不包含任何聊天记录、数据库或密钥。

---

## 目录

- [下载安装](#下载安装)
- [它解决什么问题](#它解决什么问题)
- [设计原则](#设计原则)
- [功能](#功能)
- [使用说明](#使用说明)
- [从源码运行](#从源码运行)
- [配置参考](#配置参考)
- [项目结构](#项目结构)
- [架构与调用关系](#架构与调用关系)
- [隐私与数据边界](#隐私与数据边界)
- [构建与发布](#构建与发布)
- [开发与自检](#开发与自检)
- [许可与致谢](#许可与致谢)

---

## 它解决什么问题

关于一个真实的人，你手上通常有一堆零散材料：聊天记录、事件笔记、别人的转述。直接把这些丢给大模型要结论，得到的往往是不可追溯的臆测。

Prophet 把这件事拆成可核对的两步：**先保存事实，再生成解释**。

1. 材料原样入库，带来源、时间和内容哈希。
2. 模型对每条材料输出结构化分析，写入数据库。
3. 画像在材料之上逐版累积，每版都能回溯到触发它的那条材料。
4. 对未来的预测单独记录，等事情发生后补录实际结果，形成复盘。

任何一步失败都不会覆盖已有数据。任何时候你都能看到某个结论是从哪条材料推出来的。

---

## 设计原则

| 原则 | 含义 |
|---|---|
| 事实与解释分离 | 聊天原文、画像证据、盘面和复盘是事实层；模型输出是解释层。两层分表存储，解释层可随时重建。 |
| 本机优先 | 数据库、导出文件和分析工作目录都在本机。不启动 HTTP 服务，前端不加载任何外部 CDN 资源。 |
| 失败不损坏 | 模型调用失败不写入画像；导入操作备份后再写；导入的源文件不原地修改。 |
| 两库隔离 | 人物画像与赛博算命分属两个 SQLite 文件，不隐式合并、不互相关联。 |
| 可复现 | 术式盘面由纯 Python 引擎确定性计算，带 schema 版本与快照哈希，黄金样例可对拍。 |

---

## 功能

| 页面 | 能力 | 数据写入 |
|---|---|---|
| **人物画像** | 人物管理、直接输入或上传材料、分析并保存画像、预测与复盘、历史重建与回退、人物与数据库导出 | `data/sentiment.db` |
| **聊天导出** | 从本机 QQ / 微信导出文字聊天，支持 JSON、TXT、CSV，可指定聊天对象、时间范围和保存目录。**仅 Windows** | 所选目录 |
| **聊天分析** | 选择 JSON/JSONL 聊天记录与目标发送者，通过智能助手提示词、手动命令或一键执行产出报告 | 所选目录 + `.chat-material-work/` |
| **赛博算命** | 纯 Python 实现周易、梅花、六爻、八字、紫微、奇门和大六壬，提供独立档案、历史记录、规则检索和数据库导入导出 | `data/fortune.db` |

QQ、微信导出和聊天分析都由项目内代码实现，不依赖项目目录外的脚本。

macOS 上没有"聊天导出"入口：该功能依赖 Windows 客户端的进程内存、`tasklist` 和注册表，macOS 客户端没有对应实现。导出的聊天 JSON 仍然可以在 macOS 上导入做分析。

---

## 使用说明

### 人物画像

1. 在"人物与数据"下方新建人物，或选择已有人物；背景备注最多 100 字。没有人物时也可直接导入数据库备份。
2. 在"添加材料"中直接输入文字，或在"文件导入"中选择/填写文件地址后点击"导入"。支持 `.txt`、`.md`、`.csv`、`.json`、文本型 `.pdf`、`.docx`、`.xlsx`；发生日期不能晚于今天，日期或正文无效时页面会提示原因并禁止提交。
3. 填写材料标题、发生时间和场景备注后，点击分析并保存。分析失败不会覆盖已有画像。当前画像把总览和各类画像条目分别显示为带版本或条数的独立卡片。
4. 在"预测与复盘"中输入假设事件，选择画像版本生成候选反应；事情发生后补录实际结果。两项都需要先配置模型。
5. 在"历史与导出"中查看证据、重建或回退画像。重建、回退和数据库导入都需要二次确认。选择保存目录后可导出人物 JSON、Markdown 或数据库备份，页面会显示实际路径。

### 聊天导出

1. 进入"聊天导出"，选择 QQ 或微信。
2. 填写要导出的聊天对象；留空表示全部会话。
3. 选择 JSON、TXT 或 CSV。推荐 JSON，便于后续导入和分析。
4. 时间范围默认是所有时间，也可以指定开始和结束日期。
5. 保存位置使用设置中的默认保存目录；免安装版首次运行为 `%LOCALAPPDATA%\Prophet\output`。
6. 点击"开始导出"，完成后页面会显示文件名、大小和实际保存位置。失败时任务卡只显示错误提示和重试按钮。

"高级选项"只在自动识别不到本地数据、账号或进程时使用。导出实现位于 `exporters/qq` 和 `exporters/wechat`，均为只读：不修改客户端文件，也不发送消息。

### 聊天分析

1. 填写本机聊天 JSON/JSONL 文件路径。离开输入框后页面会检查一次文件格式并显示识别到的发送者，原文件不会上传。
2. 填写目标发送者。离开输入框后，页面会在内容非空时检查是否与文件中的发送者完全一致。
3. 选择处理方式：
   - **交给 Agent**：根据当前输入生成提示词，可复制给具备本机文件和命令执行能力的 Agent。
   - **手动处理**：根据当前输入生成命令，可复制后逐批处理 Chunk、分期概括和跨期概括，并保留证据。
   - **一键执行**：聊天文件、目标发送者和保存位置齐全、自动校验通过且模型已配置后，"开始分析"才可点击。
4. 选择输出目录即可。三种方式都按 `sender-YYYYMMDD-HHMMSS.md` 命名完整报告，并生成同名 `_core` 核心报告。续跑目录自动保存在 `.chat-material-work`。

分析脚本、提示词和报告格式文件都在 `chat-material-extractor` 目录中。

### 赛博算命

先在"选择术式"卡片中选择术式，再在独立的"术式配置"卡片中填写参数，点击"起盘"保存结构化盘面。"清空结果"会恢复配置并清空当前结果，但保留当前选择的术式。

- **起卦方式**：周易、梅花和六爻使用统一的按钮式起卦。梅花默认时间起卦；数字起卦接受 1–999 的整数并由两个数字推算动爻；手动起卦以 1–8 指定上下卦、以 1–6 指定动爻，越界输入在离开输入框时提示。
- **命主档案**：八字和紫微默认使用命主档案，紫微固定按项目适配规则修正闰月。出生时间和起盘时间可选最近 100 年内的日期，不能晚于当前时间；小时和分钟需要手动输入。
- **历史记录**：以独立卡片显示所问事项、分类、时间和术式。每条可查看结果、导出报告或删除（需要二次确认）。结果区先给报告保存位置和导出按钮，再给模型解读与 agent 提示词；解读与提示词默认收起，同一时间只展开一个。
- **数据维护**：可选择文件夹备份当前数据库；导入数据库会直接替换现有数据库。

---

## 从源码运行

### 环境要求

- Windows 10/11，或 macOS 11+（Apple Silicon）
- Python 3.11 或更高版本（CI 使用 3.12）
- 可选：一个模型服务。支持 OpenAI Responses、OpenAI-compatible Chat Completions 和 Ollama。不配置模型时，导出、算命、材料入库和画像查看都照常可用，只有"分析""预测""解读"相关按钮会被锁定。
- QQ/微信导出仅支持 Windows，且需要对应客户端已登录，并允许脚本读取所需的本地文件或进程信息。

### 安装

```bash
git clone https://github.com/ZGZLCC/Prophet.git
cd Prophet
py -3.11 -m venv .venv          # macOS: python3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1    # macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
```

若 PowerShell 拒绝执行本地脚本（提示"未对文件进行数字签名"）：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 配置模型（可选）

复制 [.env.example](.env.example) 为项目根目录的 `.env`，最小配置只需四项：

```powershell
Copy-Item .env.example .env
notepad .env
```

```dotenv
LLM_PROVIDER=openai-chat
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=你的密钥
LLM_MODEL=你的模型名
```

也可以跳过这一步，直接在应用内的"设置"里填写，配置会写入 `.env`。

### 启动

```powershell
.\.venv\Scripts\python.exe desktop.py
```

只想检查页面布局时，可以用静态预览（没有 Python 桥接，只有界面没有功能）：

```powershell
.\.venv\Scripts\python.exe -m http.server 8766 --bind 127.0.0.1
```

浏览器打开 <http://127.0.0.1:8766/web/>，按 `Ctrl+C` 停止。完整功能请运行 `desktop.py`。

---

## 配置参考

系统环境变量优先于 `.env`。源码运行读取项目根目录的 `.env`；免安装版读取 `%LOCALAPPDATA%\Prophet\.env`。

| 配置项 | 说明 |
|---|---|
| `LLM_PROVIDER` | `openai-responses`、`openai-chat` 或 `ollama` |
| `LLM_API_KEY` | 服务商密钥；本地兼容服务可按服务要求填写 |
| `LLM_BASE_URL` | 可选；官方接口可留空，兼容服务填写接口地址 |
| `LLM_MODEL` | 要使用的模型名称 |
| `PROPHET_THEME` / `PROPHET_TIMEZONE` | 界面主题与显示时区；默认跟随系统、`Asia/Shanghai` 时间显示 |
| `PROPHET_OUTPUT_DIR` | 可选，默认保存目录 |
| `PROPHET_DATABASE_DIR` | 可选，默认数据库目录；修改时会分别复制两个本地数据库 |
| `APP_DB_PATH` | 可选，人物画像库路径，默认 `data/sentiment.db` |
| `FORTUNE_DB_PATH` | 可选，赛博算命库路径，默认 `data/fortune.db`，不与人物画像库合并 |
| `MAX_FILE_MB` / `MAX_TEXT_CHARS` | 可选，上传文件大小与单条文本长度上限 |
| `MAX_TABLE_ROWS` | 可选，表格类材料解析的最大行数 |
| `MAX_CHUNK_CHARS` / `CHUNK_OVERLAP_CHARS` | 可选，聊天分析的分块长度与重叠长度 |

`.env`、数据库和导出结果都不进版本库，`.gitignore` 已覆盖。

---

## 项目结构

```text
Prophet/
├─ web/                           # 四个页面的 HTML、CSS 和 JavaScript
│  ├─ modules/                    # 共享、人物画像、聊天、算命和通用前端模块
│  └─ styles/                     # 基础、页面和设计系统样式
│     └─ design-system.css        # 视觉契约与跨页面统一规则
├─ app_api.py                     # 组合并暴露 AppApi
├─ api/                           # 按页面拆分的 Python 桥接实现
│  ├─ base.py                     # 状态、校验、路径和后台任务
│  ├─ settings.py                 # 设置、版本与健康检查
│  ├─ profile.py                  # 人物画像页面接口
│  ├─ chat.py                     # 聊天导出与分析接口
│  ├─ fortune.py                  # 赛博算命页面接口
│  └─ dialogs.py                  # 原生文件/文件夹对话框
├─ person_profile/                # 人物画像核心业务
│  ├─ analysis.py                 # 模型调用、画像更新、预测和复盘
│  ├─ storage.py                  # 人物画像 SQLite 数据层
│  ├─ parsers.py                  # 材料文本解析
│  └─ export.py                   # 人物画像导出
├─ analysis.py                    # 兼容旧导入的薄封装
├─ storage.py                     # 兼容旧导入的薄封装
├─ parsers.py                     # 兼容旧导入的薄封装
├─ profile_export.py              # 兼容旧导入的薄封装
├─ fortune_app.py                 # 七术式原生应用服务
├─ fortune/                       # 纯 Python 引擎、语料、规则与独立数据层
├─ background_jobs.py             # 模型连接检查等后台任务
├─ desktop.py                     # 桌面窗口启动入口
├─ chat_export.py                 # Windows 导出脚本调用封装
├─ chat_analysis.py               # 聊天分析命令与报告构建封装
├─ exporters/
│  ├─ qq/                         # QQ Windows 导出实现
│  └─ wechat/                     # 微信 Windows 导出实现
├─ chat-material-extractor/
│  ├─ scripts/extract.py          # 聊天材料整理和报告构建
│  ├─ prompts/                    # 分析提示词
│  └─ references/                 # 报告格式说明
├─ process_runner.py              # 可取消的本机子进程执行
├─ platform_support.py            # 平台数据目录、深色模式、窗口图标与能力开关
├─ assets/                        # 应用图标、主题自适应图标和许可说明
├─ build_windows.ps1              # Windows 打包脚本
├─ build_macos.sh                 # macOS 打包脚本（含 .icns 生成）
├─ test_core.py                   # 核心流程自检
├─ test_fortune.py                # 术式引擎对拍测试
├─ tests/fortune_fixtures/        # 术式引擎黄金样例
├─ docs/CODE_STRUCTURE.md         # 代码职责和调用关系
├─ docs/DESIGN-webflow.md         # 前端视觉设计参考
├─ .github/workflows/             # CI：构建、自检并发布免安装版
├─ requirements.txt               # Python 依赖
├─ .env.example                   # 配置模板
├─ LICENSE                        # 项目主许可证
├─ NOTICE.md                      # 第三方图标、导出实现和语料许可
├─ data/                          # 运行时 SQLite 数据库（不提交）
└─ output/                        # 默认导出目录（不提交）
```

完整的模块职责和调用关系见 [docs/CODE_STRUCTURE.md](docs/CODE_STRUCTURE.md)。

`person_profile/`、`fortune/`、`exporters/` 和 `chat-material-extractor/` 是相互独立的核心实现与资源目录。`fortune/data` 与 `fortune/schemas` 是随源码分发的只读语料和结构定义，不是运行时数据；用户数据一律写入 `data/` 或 `%LOCALAPPDATA%\Prophet`，不要写回安装目录。

---

## 架构与调用关系

```text
desktop.py → pywebview → web/ → app_api.py
                               ├─ api/profile.py  → person_profile/ → data/sentiment.db
                               ├─ api/settings.py → .env / 本地数据库路径
                               ├─ api/chat.py     → chat_export.py / chat_analysis.py
                               ├─ api/fortune.py  → fortune_app.py → fortune/ → data/fortune.db
                               └─ api/dialogs.py  → pywebview 原生文件对话框
```

| 层 | 职责 |
|---|---|
| `web/` | 四个页面的界面、浅色/深色主题、导航和键盘操作。只负责渲染与交互，不实现 Python 业务。 |
| `app_api.py` | 唯一的 JS–Python 桥接层，组合并暴露稳定的 `AppApi`。 |
| `api/` | 信任边界。按页面组织方法，负责输入校验、路径解析、错误码和后台任务。 |
| `person_profile/` | 人物画像的分析、存储、解析和导出核心，只接收明确参数和数据库路径。 |
| `fortune/` | 纯 Python 术式引擎、规则语料、Schema 和独立数据层。 |
| `exporters/` | Windows QQ/微信导出实现，只读。 |
| `chat-material-extractor/` | 聊天规范化、分块、分期、模型调用和报告构建。 |
| `platform_support.py` | 按平台解析数据目录、系统深色模式、窗口图标，并声明可用能力（如聊天导出）。 |

`background_jobs.py` 承载聊天导出、聊天分析和模型解读等耗时任务，切换页面不会阻塞。`process_runner.py` 提供可取消的本机子进程执行。

`person_profile/analysis.py` 使用标准库 HTTP 客户端，支持 OpenAI Responses、OpenAI-compatible Chat Completions 和 Ollama 三种协议。

两份数据库严格隔离：`data/sentiment.db` 只存人物画像、材料、预测与复盘；`data/fortune.db` 只存术式档案、盘面和复盘。两库不得隐式合并或互相关联。首次运行尚未创建数据库属于正常状态。

前端视觉系统以 [docs/DESIGN-webflow.md](docs/DESIGN-webflow.md) 为参考：白色画布、近黑色主操作、4px 控件圆角与 8px 卡片圆角、正文 16px、界面字重不超过 600，并提供浅色/深色主题、可见键盘焦点、减少动画支持和响应式适配。

---

## 隐私与数据边界

- **默认不联网**。导出、术式起盘、材料入库、画像查看和复盘全部在本机完成，不需要网络。
- **只有解释需要模型**。配置云端模型时，提交给模型的材料文本会离开本机；使用前请确认服务商政策和材料授权范围。需要完全离线时，接本机 Ollama 或兼容接口的本地模型服务。
- **前端不请求外部资源**。页面不加载 CDN 字体、统计脚本或任何第三方脚本。
- **API Key 只从环境变量或 `.env` 读取**，不写入数据库、日志、导出文件或报告。
- **绑定本机位置**。数据库、导出结果和分析工作目录都在本机；应用不启动 HTTP 服务，也不监听端口。
- **只读导出**。QQ/微信导出不修改客户端数据，不发送消息。
- **可撤回**。人物删除、材料停用、画像历史回退都在页面内提供，删除会级联清理该人物的关联记录。

导出功能只应用于你自己有权保存和分析的聊天记录。处理他人的材料前，请确认你已获得相应授权。

---

## 构建与发布

免安装版由 GitHub Actions 构建，本机不需要打包环境：Windows 在 `windows-latest`，macOS 在 `macos-latest`（arm64）。

**发布新版本**：推送版本标签即可，两个平台会同时构建并写进同一个 Release。

```powershell
git tag v1.1.0
git push origin v1.1.0
```

Release 中会附上 `Prophet-windows-x64.zip`、`Prophet-macos-arm64.zip` 及各自的 `.sha256`。构建流程见 [.github/workflows/build-windows.yml](.github/workflows/build-windows.yml) 与 [.github/workflows/build-macos.yml](.github/workflows/build-macos.yml)：先跑一遍自检，再打包，然后对产物执行 `--self-test`，只有全部通过才会发布。推到 `main` 或提交 PR 时也会构建，但不发布，只保留 Actions artifact（默认 30 天）。

> 面向普通用户请始终使用 Release 里的压缩包。Actions artifact 由 GitHub 自己再包一层 zip：Windows 的 artifact 里是文件，解压一次即可；macOS 的 `.app` 必须保持可执行权限，所以 artifact 里放的是完整 zip，需要解压两次。

**本地构建**（可选，必须在目标平台上执行，PyInstaller 无法交叉编译）：

```powershell
# Windows
.\.venv\Scripts\python.exe -m pip install "pyinstaller>=6.15,<7"
.\build_windows.ps1
```

```bash
# macOS
pip install "pyinstaller>=6.15,<7"
bash ./build_macos.sh
```

产物分别是 `dist-native/Prophet`（Windows）和 `dist-native/Prophet.app`（macOS）。Windows 脚本会自动选用 `.venv\Scripts\python.exe`，也可以用 `-Python` 指定其他解释器；macOS 脚本会用 `sips` 和 `iconutil` 从 `assets/prophet_icon_light.png` 合成 `.icns`。两个脚本都会在结束时对产物执行一次 `--self-test`。

`--self-test` 除了校验依赖、解析器和术式引擎，还会加载一次 pywebview 的窗口后端：Windows 检查 `webview.platforms.winforms`（pythonnet + .NET Framework），macOS 检查 `webview.platforms.cocoa`（PyObjC）。缺依赖时会在打包阶段就失败并给出原因，而不是等到双击才弹出错误框。

---

## 开发与自检

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q desktop.py app_api.py api person_profile analysis.py storage.py parsers.py profile_export.py chat_export.py chat_analysis.py fortune_app.py platform_support.py
.\.venv\Scripts\python.exe test_core.py
.\.venv\Scripts\python.exe test_fortune.py
.\.venv\Scripts\python.exe desktop.py --self-test
.\.venv\Scripts\python.exe chat-material-extractor\scripts\extract.py self-test
```

改动源码、前端、配置或文档后，重新执行对应平台的打包脚本（`build_windows.ps1` / `build_macos.sh`）并确认产物 `--self-test` 通过。

提交前请确保没有把 `.env`、数据库文件、导出结果或构建产物加入版本库。

---

## 许可与致谢

项目代码以 [MIT](LICENSE) 许可发布，版权归 ZGZLCC。

第三方内容按各自的许可分发，详见 [NOTICE.md](NOTICE.md)：

- 应用图标派生自 [Lucide](https://lucide.dev/icons/compass) 的 `compass`（MIT）
- `exporters/wechat/wechat_db.py` 的微信数据库读取实现源自 **wechatauto** 项目（Apache-2.0）
- `fortune/data/corpus/zhouyi.jsonl` 与 `yizhuan.jsonl` 整理自[维基文库《周易（四部叢刊本）》](https://zh.wikisource.org/zh/周易_(四部叢刊本))，依 **CC BY-SA 4.0** 分发，**不受 MIT 覆盖**
- `fortune/data/corpus/` 下的其余规则语料是本项目整理的摘录与研究边界，随本项目按 MIT 分发

感谢维基文库的录入者和上述开源项目的作者。
