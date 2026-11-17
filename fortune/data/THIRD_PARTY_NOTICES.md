# 第三方来源与许可声明

本项目代码以根目录 [LICENSE](../LICENSE) 的 MIT 许可发布。下列内容来自第三方，或按不同许可分发。

## 《周易》古籍语料

`fortune/data/corpus/zhouyi.jsonl` 与 `fortune/data/corpus/yizhuan.jsonl` 整理自维基文库《周易（四部叢刊本）》。

- 来源：<https://zh.wikisource.org/zh/周易_(四部叢刊本)>
- 固定修订：卷次与 `oldid` 逐条记录在 `fortune/data/corpus/source-snapshot.json`
- 许可：原作页面标示为公有领域；电子录文按维基文库页面说明以 **CC BY-SA 4.0** 提供，要求署名与相同方式共享
- 许可全文：<https://creativecommons.org/licenses/by-sa/4.0/>
- 范围：只整理卦名、卦辞、彖传、大象、爻辞和小象，不包含现代白话译注；CText 仅作版本与字词交叉核对线索，其文本未打包进项目

这两份 JSONL 文件按 CC BY-SA 4.0 分发，**不适用**本项目的 MIT 许可。再分发或修改时须保留上述署名和许可声明。逐条记录的 `rights` 字段同样声明了该边界。

## 项目规则语料

`fortune/data/corpus/` 下的 `meihua.jsonl`、`liuyao.jsonl`、`bazi.jsonl`、`ziwei.jsonl`、`qimen.jsonl` 和 `liuren.jsonl` 是本项目整理的规则摘录与研究边界，不是任何流派的完整古籍文本，随本项目按 MIT 分发。

## 应用图标

图标派生自 Lucide 的 `compass` 图标（经由 Feather Icons），MIT 许可。

- Lucide：<https://lucide.dev/icons/compass>
- 许可与版权声明全文见 `assets/ICON_LICENSE.txt`

## 微信数据库读取实现

`exporters/wechat/wechat_db.py` 承载微信 4.x 本地 SQLCipher 数据库的只读读取与解密实现，源自 **wechatauto** 项目，按 **Apache License 2.0** 分发。

- 许可全文见 `exporters/wechat/THIRD_PARTY_LICENSE.txt`
- 本项目仅作只读封装用于导出当前用户自己的聊天文字，不修改微信文件，也不发送消息

## Python 依赖

正式运行依赖以 `requirements.txt` 为准。下表列出直接依赖及其许可，精确版本见安装时的解析结果。

| 依赖 | 用途 | 许可 |
|---|---|---|
| [jsonschema](https://pypi.org/project/jsonschema/) | 术式 facts、Schema 和语料校验 | MIT |
| [pypdf](https://pypi.org/project/pypdf/) | 文本型 PDF 材料解析 | BSD-3-Clause |
| [python-docx](https://pypi.org/project/python-docx/) | `.docx` 材料解析 | MIT |
| [openpyxl](https://pypi.org/project/openpyxl/) | `.xlsx` 材料解析 | MIT |
| [cryptography](https://pypi.org/project/cryptography/) | 本地数据库解密的加密原语 | Apache-2.0 OR BSD-3-Clause |
| [pywebview](https://pypi.org/project/pywebview/) | 桌面窗口宿主 | BSD-3-Clause |
| [lunar-python](https://pypi.org/project/lunar-python/) | 农历与节气换算 | MIT |
| [izthon](https://pypi.org/project/izthon/) | 紫微斗数排盘内核（固定 `0.2.x`） | MIT |
| [tzdata](https://pypi.org/project/tzdata/) | Windows 上的 IANA 时区数据（`ZoneInfo` 依赖） | Apache-2.0 |

构建免安装版时另需 PyInstaller（GPL-2.0-or-later，带启动器例外）；它只用于打包，不是运行时依赖。

## 运行边界

- 古籍数据从本地 JSONL 读取，正常运行时不会请求 Wikisource、CText 或其他远程内容接口。
- 模型调用只发送需要解释的文字；API Key 从环境变量或 `.env` 读取，不写入数据库、日志或导出文件。
- 本项目不声明对上述第三方内容的任何额外权利。
