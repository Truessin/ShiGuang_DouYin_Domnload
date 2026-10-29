# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [2.1.0] - 2026-10-29

### 修复

- 修正图集图片源选择顺序：优先使用页面提供的 `origin_image` / `display_image` / 展示地址，而不是 `download_url_list`。v2.0 将 `download_url_list` 作为首选，导致部分作品保存了带平台水印的图片。
- 新增已知平台水印模板过滤（如 `tplv-dy-water-v2`）与查询参数检测。
- 当某张图片只有带平台水印的地址时明确报错并停止，不再静默使用带水印版本。
- 新增 3 项图集水印回归测试。

### 变更

- 版本号集中到 `version.py`，界面标题与发布包共用。
- 项目整理为可公开发布的结构：拆分用户文档、开发文档、隐私说明、FAQ、验证记录与第三方许可证。
- 新增 GitHub Actions CI、Issue / PR 模板、依赖更新配置与代码检查配置。
- 构建脚本改为在打包前强制运行测试与 `ruff`，并自动生成带版本号的 ZIP。

## [2.0.0] - 2026-10

### 新增

- PyQt6 桌面界面，支持粘贴分享文案、批量链接、文件列表与进度展示。
- 完整图集识别：按作品编号匹配图片清单，保持原顺序，排除封面、头像与推荐内容。
- 基于本机 Edge / Chrome 的 Playwright 解析兜底与独立登录资料目录。
- 停止、`.part` 清理、重复文件另存、SHA-256 清单与真实格式扩展名。
- 视频按分辨率与码率选择页面提供的最高版本。
- 离线测试与离屏界面测试。

### 说明

- 不支持跨次断点续传、主页批量抓取、直播与私密内容。
- 不绕过登录、验证码或平台访问限制。

## [1.0.0] - 初始版本

- 基于早期 `douyin_downloader.py` / `douyin_browser.py` 脚本的命令行下载功能。

[2.1.0]: https://github.com/Truessin/shiguang-downloader/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/Truessin/shiguang-downloader/releases/tag/v2.0.0
