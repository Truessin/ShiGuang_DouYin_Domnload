# 隐私与安全

## 数据存放位置

程序在自身目录下使用两个文件夹：

| 路径 | 内容 | 敏感性 |
| --- | --- | --- |
| `downloads/` | 下载的媒体文件与 `作品信息.json` | 取决于作品内容，可能涉及他人著作权 |
| `data/settings.json` | 上次选择的保存目录 | 含本机路径 |
| `data/browser-profile/` | 专用浏览器的缓存、Cookie、登录状态 | **高，等同账号凭据** |

`data/browser-profile` 是你登录后产生的本机状态，**不要上传到 GitHub、网盘或发送给他人**。

## 程序如何处理你的数据

- 不读取、不导入你日常浏览器的账号、密码、Cookie 或历史记录。
- 不访问第三方代解析网站；解析与下载均在本机直接连接抖音及其 CDN。
- 不上传作品、输入内容、登录状态或使用统计。
- 不包含遥测、崩溃上报或广告 SDK。
- `作品信息.json` 只写入作品元数据、文件大小、尺寸与 SHA-256，**不写入签名 URL、Cookie 或请求头**。
- 日志仅显示在界面中，不写入磁盘。

## 网络访问范围

程序只允许访问：

- 分享页域名：`douyin.com`、`iesdouyin.com`
- 媒体域名：上述域名及 `douyinvod.com`、`douyincdn.com`、`byteimg.com`、`douyinpic.com`、`ibytedtos.com`、`snssdk.com`、`pstatp.com`、`bytecdn.cn`、`douyinstatic.com`、`toutiaoimg.com`、`ixiguavideo.com`、`bytegoofy.com`、`bytefcdn.com`

所有跳转都会逐跳校验目标地址；带用户名 / 密码、非标准端口或指向内网 / 本机的地址会被拒绝，以降低被恶意链接利用的风险。

## 分享页脚本

页面内嵌数据只作为 JSON 解析，**不会执行**分享页面中的 JavaScript。浏览器兜底模式使用真实的 Edge / Chrome 加载页面，此时页面脚本由浏览器自身执行，与正常访问抖音网页一致。

## 账号安全建议

- 使用专用浏览器资料目录登录，不要在里面保存与下载无关的高价值账号。
- 定期删除 `data/browser-profile` 可清除本机登录状态。
- 不要把 `data` 目录打包进任何发布物；项目的 `.gitignore` 已排除该目录。
- 在公共电脑上使用后，建议删除整个 `data` 目录。

## 报告安全问题

如果发现域名校验绕过、路径穿越、任意文件写入、凭据泄露等问题，请勿公开提交 Issue。请按 [SECURITY.md](../SECURITY.md) 中的方式私下联系维护者，并附上复现步骤与影响范围。
