# 第三方来源与许可

本项目代码以 [LICENSE](LICENSE) 的 MIT 许可发布，版权归 ZGZLCC。下列内容来自第三方或按不同许可分发，**不受 MIT 覆盖**。

完整的第三方依赖与语料声明见 [`fortune/data/THIRD_PARTY_NOTICES.md`](fortune/data/THIRD_PARTY_NOTICES.md)（随免安装包一起分发）。本文是仓库级别的汇总。

## 应用图标

图标派生自 Lucide 的 `compass` 图标（经由 Feather Icons），MIT 许可。

- Lucide：<https://lucide.dev/icons/compass>
- 版权与许可全文：`assets/ICON_LICENSE.txt`

## 微信数据库读取实现

`exporters/wechat/wechat_db.py` 承载微信 4.x 本地 SQLCipher 数据库的只读读取与解密实现，源自 **wechatauto** 项目，按 **Apache License 2.0** 分发。

- 许可全文：`exporters/wechat/THIRD_PARTY_LICENSE.txt`
- 本项目只作只读封装，导出当前用户自己的聊天文字；不修改微信文件，也不发送消息

## 《周易》古籍语料

`fortune/data/corpus/zhouyi.jsonl` 与 `fortune/data/corpus/yizhuan.jsonl` 整理自维基文库《周易（四部叢刊本）》。

- 来源：<https://zh.wikisource.org/zh/周易_(四部叢刊本)>
- 固定修订：卷次与 `oldid` 逐条记录在 `fortune/data/corpus/source-snapshot.json`
- 许可：原作页面标示为公有领域；电子录文按维基文库页面说明以 **CC BY-SA 4.0** 提供，要求署名与相同方式共享
- 许可全文：<https://creativecommons.org/licenses/by-sa/4.0/>

这两份 JSONL 文件按 CC BY-SA 4.0 分发。再分发或修改时须保留上述署名和许可声明。

`fortune/data/corpus/` 下的 `meihua.jsonl`、`liuyao.jsonl`、`bazi.jsonl`、`ziwei.jsonl`、`qimen.jsonl` 和 `liuren.jsonl` 是本项目整理的规则摘录与研究边界，不是任何流派的完整古籍文本，随本项目按 MIT 分发。

## Python 依赖

正式运行依赖见 [`requirements.txt`](requirements.txt)。直接依赖及其许可：

| 依赖 | 用途 | 许可 |
|---|---|---|
| jsonschema | 术式 facts、Schema 和语料校验 | MIT |
| pypdf | 文本型 PDF 材料解析 | BSD-3-Clause |
| python-docx | `.docx` 材料解析 | MIT |
| openpyxl | `.xlsx` 材料解析 | MIT |
| cryptography | 本地数据库解密的加密原语 | Apache-2.0 OR BSD-3-Clause |
| pywebview | 桌面窗口宿主 | BSD-3-Clause |
| lunar-python | 农历与节气换算 | MIT |
| izthon | 紫微斗数排盘内核（固定 `0.2.x`） | MIT |

构建免安装版时另需 PyInstaller（GPL-2.0-or-later，带启动器例外）；它只用于打包，不是运行时依赖。

## 免责声明

本项目是本地个人工具，不提供心理诊断、医学建议、投资建议或对未来的可靠预测。术数结果与模型输出都是基于已有材料的推断，不是事实认定。使用聊天导出功能前，请确认你有权处理相关记录。
