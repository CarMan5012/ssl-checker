# 🛡️ SSL-Monitor: 企业级 SSL 证书到期巡检告警工具

`SSL-Monitor` 是一款专为企业环境设计的轻量化 SSL 证书巡检告警工具。通过 Docker 容器化部署，支持钉钉机器人安全模式（加签+自定义关键词）、动态多级告警天数配置、邮箱报警和智能节假日补发机制，彻底规避因证书过期导致的服务中断风险。

---

## ✨ 核心特性

- **动态阶梯告警阈值**：支持自定义配置 `ALERT_INFO_DAYS` (提醒，默认 14 天)、`ALERT_WARNING_DAYS` (警告，默认 7 天) 和 `ALERT_CRITICAL_DAYS` (严重，默认 3 天) 触发阈值。
- **智能节假日补发**：内置节假日感知逻辑（默认对接 `timor.tech` API）。在非工作日（周末或法定节假日）触发的低级告警将延期至收假后第一个工作日早上补发，防止报警在非工作时间被淹没。
- **防报警消息风暴**：本地持久化保存每个域名的告警状态（如 `提醒`/`警告`/`严重`/`正常`），只有在告警状态发生变化（如从“提醒”变为“警告”）或首个工作日补发时才会触发出方向通知。
- **安全加签与关键词**：全面适配钉钉机器人的 **签名验证 (HMAC-SHA256)** 和 **自定义关键词** 安全规则，防止消息发送被拦截。
- **支持 URL/主机端口/注释智能解析**：在配置文件中支持直接粘贴 URL（如 `https://example.com/api`），自动剥离协议与路径；同时支持添加 `# 行内注释`。
- **每日随机选点巡检**：定时循环任务在每天上午 `09:00 - 09:59` 之间随机时间启动，避免固定的 API 调用特征。
- **原子状态写入**：采用 `tempfile` 临时写入后覆盖原文件的原子更新设计，保证 JSON 状态文件不因容器重启或宕机而损坏。

---

## 🚀 快速开始

### 1. 准备本地配置目录
在您的宿主机创建 `conf` 目录，并放置域名列表文件 `websites_list.txt`：
```bash
mkdir -p ./conf
cat <<EOF > ./conf/websites_list.txt
# 每一行填写一个域名，支持端口与行内注释
example.com                   # 默认检测 443 端口
https://www.runoob.com        # 协议前缀与后缀会自动剥离
my-custom-port.com:8443       # 支持非 443 自定义端口
EOF
```

### 2. 启动生产环境容器
挂载配置目录，脚本会自动在其中创建并管理状态记录文件 `ssl_alert_state.json`。
```bash
docker run -d \
  --name ssl-monitor \
  --restart always \
  -v $(pwd)/conf:/app/conf \
  -e TZ=Asia/Shanghai \
  -e DINGTALK_TOKEN="您的钉钉Token" \
  -e DINGTALK_SECRET="您的加签Secret(可选)" \
  -e DINGTALK_KEYWORD="您的自定义关键词(可选)" \
  carman5012/ssl-monitor:v1.0.0
```

### 3. 测试模式（立即运行并退出）
添加 `-e TEST_MODE=true` 环境变量开启测试模式。开启后，容器会立即启动一次巡检，并向钉钉/邮箱发送带 `[TEST]` 前缀的测试告警，且不会把这次告警记录到状态文件中，非常适合用来测试网络连接和钉钉/邮箱配置是否正常。
```bash
docker run --rm \
  -v $(pwd)/conf:/app/conf \
  -e TZ=Asia/Shanghai \
  -e TEST_MODE=true \
  -e DINGTALK_TOKEN="您的钉钉Token" \
  -e DINGTALK_SECRET="您的加签Secret(可选)" \
  -e DINGTALK_KEYWORD="您的自定义关键词(可选)" \
  carman5012/ssl-monitor:v1.0.0
```
---

## ⚙️ 环境变量说明

| 环境变量名 | 是否必填 | 默认值 | 说明 |
| :--- | :---: | :--- | :--- |
| `LIST_FILE` | 否 | `websites_list.txt` | 域名列表文件名，若仅指定文件名，则默认在挂载目录中加载 |
| `STATE_FILE` | 否 | `ssl_alert_state.json`| 告警状态存储文件名，默认在挂载目录下自动生成并管理 |
| `DINGTALK_TOKEN` | 否 | - | 钉钉机器人的 Access Token（配置后自动拼装成完整 Webhook 链接，推荐） |
| `DINGTALK_WEBHOOK`| 否 | - | 钉钉机器人的 Webhook 完整地址（兼容直接配置完整 URL） |
| `DINGTALK_SECRET` | 否 | - | 钉钉机器人的签名密钥（加签设置） |
| `DINGTALK_KEYWORD`| 否 | - | 钉钉机器人的自定义匹配关键词（非必要时可为空） |
| `ALERT_INFO_DAYS` | 否 | `14` | 提醒等级阈值（天数，证书过期天数少于或等于该值时触发提醒等级告警） |
| `ALERT_WARNING_DAYS` | 否 | `7` | 警告等级阈值（天数，证书过期天数少于或等于该值时触发警告等级告警） |
| `ALERT_CRITICAL_DAYS`| 否 | `3` | 严重等级阈值（天数，证书过期天数少于或等于该值时触发严重等级告警） |
| `SMTP_HOST` | 否 | - | 邮件发送 SMTP 服务器主机地址 |
| `SMTP_PORT` | 否 | `465` | SMTP 服务器端口（使用 SSL，默认 465） |
| `SMTP_USER` | 否 | - | 邮件发送账号用户名 |
| `SMTP_PASS` | 否 | - | 邮件发送账号授权密码 |
| `EMAIL_TO` | 否 | - | 接收警报邮件的收件箱（多个用英文逗号分隔） |
| `TEST_MODE` | 否 | `false` | 设置为 `true` 开启单次测试模式，运行后发送测试内容并直接退出 |
| `TZ` | 否 | `Asia/Shanghai` | 容器运行时区，推荐设置为北京时间防止状态判断产生时差 |
