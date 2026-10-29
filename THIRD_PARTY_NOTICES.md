# 第三方组件声明

本项目以 GPL-3.0 发布，并依赖以下开源组件。运行时组件的许可证原文保存在 [`third_party_licenses/`](third_party_licenses/) 中。

## 运行时依赖

| 组件 | 用途 | 许可证 |
| --- | --- | --- |
| [PyQt6](https://pypi.org/project/PyQt6/) | 桌面界面绑定 | GPL-3.0（或商业许可） |
| [Qt 6](https://www.qt.io/)（PyQt6-Qt6） | 界面运行时 | LGPL-3.0 / GPL-3.0（或商业许可） |
| [requests](https://pypi.org/project/requests/) | HTTP 请求 | Apache-2.0 |
| [urllib3](https://pypi.org/project/urllib3/) | HTTP 连接池 | MIT |
| [certifi](https://pypi.org/project/certifi/) | CA 证书 | MPL-2.0 |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/) | 字符集检测 | MIT |
| [idna](https://pypi.org/project/idna/) | 国际化域名 | BSD-3-Clause |
| [Playwright](https://pypi.org/project/playwright/) | 浏览器自动化 | Apache-2.0 |
| [greenlet](https://pypi.org/project/greenlet/) | Playwright 协程支持 | MIT |
| [pyee](https://pypi.org/project/pyee/) | 事件发射器 | MIT |

## 开发与构建依赖

以下依赖仅用于开发、测试与打包，不随发布包分发：

| 组件 | 用途 | 许可证 |
| --- | --- | --- |
| [pytest](https://pytest.org/) | 测试框架 | MIT |
| [ruff](https://docs.astral.sh/ruff/) | 代码检查 | MIT |
| [PyInstaller](https://pyinstaller.org/) | 打包 | GPL-2.0-or-later（含例外条款） |

## 浏览器

程序不捆绑 Chromium 或其他浏览器内核，运行时复用用户本机安装的 Microsoft Edge 或 Google Chrome，其许可与更新由浏览器提供方负责。

## 平台内容

`downloads/` 中的媒体文件不属于本项目，也不在 GPL-3.0 的授权范围内。下载内容的权利归原作者或权利人所有；使用者应自行确认保存与再使用行为合法。

## 许可兼容性说明

PyQt6 以 GPL-3.0 提供，因此本项目整体采用 GPL-3.0。如果你需要在闭源或商业项目中分发基于本代码的衍生作品，应自行评估并取得 Qt / PyQt 的商业许可，或替换界面层实现。
