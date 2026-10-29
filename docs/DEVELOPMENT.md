# 开发与构建

## 环境

- Windows 10 / 11
- Python 3.11+（CI 覆盖 3.11 与 3.13）
- Microsoft Edge 或 Google Chrome（运行浏览器解析时需要）

```powershell
git clone https://github.com/Truessin/shiguang-downloader.git
cd shiguang-downloader
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 运行

```powershell
.\.venv\Scripts\python.exe app.py
```

调试入口：

```powershell
# 离屏启动并保存 smoke.png / smoke.json，不联网
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe app.py --smoke-test

# 仅验证链接解析（联网），结果写入 engine-verification.json
.\.venv\Scripts\python.exe app.py --verify-link "https://v.douyin.com/xxxx/"
```

## 架构

```text
┌──────────────────────────── app.py ────────────────────────────┐
│ Window (Qt 主线程)                                             │
│   ├─ 输入 / 队列 / 进度 / 文件列表                             │
│   └─ Worker (QThread) ── message signal ──► Window.on_message  │
└───────────────────────────────┬────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────┐
│ core.py                                                        │
│   extract_links → post_id → Engine.resolve                     │
│        ├─ 分享页 HTML → state_objects → find_item → parse_item │
│        ├─ 详情接口 JSON → find_item → parse_item               │
│        └─ browser.browser_resolve (Playwright 兜底)            │
│   Engine.download → 候选地址 → 校验 → 原子落盘 → 作品信息.json │
└───────────────────────────────┬────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────┐
│ browser.py                                                     │
│   Playwright + launch_persistent_context + 本机 Edge / Chrome  │
│   监听 /aweme/* 响应 + 读取页面 JSON 状态 + 同步 Cookie         │
└────────────────────────────────────────────────────────────────┘
```

### 模块职责

| 文件 | 职责 |
| --- | --- |
| `app.py` | 界面、后台线程、事件消息、设置读写、命令行调试入口 |
| `core.py` | 链接提取与域名校验、页面 JSON 解析、媒体候选选择、流式下载、格式与完整性校验、清单生成 |
| `browser.py` | 定位本机浏览器、持久化资料目录、登录窗口、解析兜底、Cookie 同步 |
| `version.py` | 版本号单一来源，界面标题与发布包版本共用 |
| `tests/` | `test_core.py`（离线逻辑）、`test_ui.py`（离屏 Qt） |
| `tools/capture_screenshot.py` | 使用示例数据离屏生成 README 界面截图，不联网 |

### 关键设计约束

1. **只解析 JSON，不执行页面脚本**：`state_objects()` 使用 `JSONDecoder.raw_decode`，不会 `eval` 分享页面内容。
2. **域名白名单**：分享页只允许抖音域名；媒体只允许抖音及已知 CDN 域名。重定向逐跳校验，拒绝内网、非标准端口与带用户信息的 URL。
3. **作品编号严格匹配**：`find_item()` 要求 `aweme_id` 与目标一致，避免误下推荐作品或页面上的其他图片。
4. **不虚构成功**：字节数为 0、长度与 `Content-Length` 不符、文件头无法识别时均抛错；`.part` 文件在 `finally` 中清理。
5. **原子落盘**：先写隐藏的 `.part`，校验通过后 `os.replace()` 重命名，避免半成品出现在结果目录。
6. **不静默降级**：图集只找到带平台水印的地址时直接报错；视频候选全部失败时整体标记失败。

### 媒体选择顺序

图集候选字段：`origin_image` → `originImage` → `url_list` → `urlList` → `display_image` → `displayImage` → `download_url_list` → `downloadUrlList`。合并后去重并过滤 `has_platform_watermark()` 命中的地址。

视频：汇总 `bit_rate` 与 `play_addr` / `play_addr_h264` / `play_addr_265` 等，按 `(宽 × 高, 码率, 非下载地址)` 降序选择。

## 测试

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest
```

当前共 24 项测试，覆盖：

- 分享文案中的链接提取、末尾标点清理、重复链接去重
- 域名、端口、用户信息与重定向校验
- 图集顺序、嵌套结构、缺图报错
- 视频分辨率与码率选择
- `aweme_id` 不匹配时拒绝解析
- 页面 JSON 状态解析（不执行脚本）
- Windows 保留文件名与非法字符
- 实际扩展名、清单不写入签名 URL、重复下载不覆盖
- 非媒体响应、截断下载、停止后清理 `.part`
- 水印模板识别与不带水印的候选回退
- Qt 空输入、完整生命周期、失败项不标记为完成

修改解析逻辑时请补充对应测试；不要为了让测试通过而放宽“完整性”或“不降级”约束。

## 代码风格

- 4 空格缩进，UTF-8，LF 换行。
- 行宽 120，`ruff` 规则集为 `E4/E7/E9/F/I/W`。
- 公开函数与关键安全逻辑保留简短注释；界面文案使用中文。
- 不在代码中写入 Cookie、真实用户路径或测试账号。

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff check --fix .
```

## 打包 Windows 发布包

```powershell
.\build.ps1
```

脚本依次执行：

1. 创建 / 复用 `.venv` 并安装 `requirements-dev.txt`
2. 在 `QT_QPA_PLATFORM=offscreen` 下运行全部测试
3. 运行 `ruff check`
4. 使用 PyInstaller `--onedir --windowed` 打包，收集 Playwright 运行时
5. 删除会遮蔽系统 ICU 的私有 `icuuc.dll` / `icudt78.dll`
6. 复制使用说明、许可证与第三方声明
7. 生成 `dist\Shiguang-v<版本>-win64.zip`

产物结构：

```text
dist/
├── Shiguang/
│   ├── Shiguang.exe
│   ├── _internal/
│   ├── 使用说明.md
│   ├── LICENSE
│   └── THIRD_PARTY_NOTICES.md
└── Shiguang-v2.1.0-win64.zip
```

发布新版本时：

1. 更新 `version.py`、`CHANGELOG.md`。
2. 在干净环境运行 `build.ps1`。
3. 在 GitHub 创建与版本号一致的标签（如 `v2.1.0`），上传 ZIP 到 Release。
4. Release 说明中注明支持的 Windows 版本、是否需要 Edge / Chrome，以及已知限制。

## 提交前检查清单

- [ ] `pytest` 全部通过
- [ ] `ruff check .` 通过
- [ ] 未提交 `data/`、`downloads/`、`.venv/`、`dist/`
- [ ] 未包含真实 Cookie、手机号、用户路径或他人作品文件
- [ ] 文档中的功能描述与实际行为一致
