# 🛡️ SSL-Monitor: 企业级证书到期巡检告警工具

`SSL-Monitor` 是一款专为企业环境设计的轻量化 SSL 证书巡检工具。它具备智能的**节假日感知能力**、**三级阶梯告警策略**以及**状态持久化机制**，在确保不遗漏风险的同时，最大限度减少非必要消息的骚扰。

---

## ✨ 核心特性

-   **智能节假日补发**：🚀 **核心亮点**。自动对接国家法定节假日 API，若告警发生在非工作日（周末或节假日），脚本会在收假后的第一个工作日自动补发一次提醒，确保风险不被淹没。
-   **启动即巡检**：容器启动后立即执行一次全量巡检，确保状态文件生成并第一时间报告风险，无需等待定时任务。
-   **阶梯告警策略**：支持配置专业级阈值，默认 14天(提醒)、7天(警告)、3天(严重)，等级清晰，逻辑严密，可通过环境变量自定义。
-   **防消息风暴**：记录每个域名的告警状态，**仅当风险等级提升**（如提醒变为警告）或**假期后首个工作日**时才发送通知。
-   **每日随机巡检**：生产模式下，每天上午 `09:00 - 09:59` 之间随机选点执行，模拟人工巡检节奏。
-   **Docker 化最佳实践**：支持配置目录整体挂载，彻底解决 Docker 挂载非持久化文件导致“文件变目录”的经典问题。
-   **钉钉安全认证支持**：支持钉钉机器人安全设置中的**自定义关键词**与**加签（签名校验）**，保障接口安全。
-   **详尽发送日志与排错**：在测试模式下或钉钉发送失败时，控制台将自动打印出详细的请求地址、发送 Payload、HTTP 状态码以及钉钉返回的 errcode 和 errmsg，便于快速排查故障。

---

## 🚀 快速开始 (Docker)

镜像已托管至 Docker Hub: `carman5012/ssl-monitor`

### 1. 准备配置目录
在宿主机创建配置文件夹，并放入域名列表文件：
```bash
mkdir -p ./conf
# 创建域名列表 (支持行内注释、协议过滤以及路径剔除)
cat <<EOF > ./conf/websites_list.txt
example.com                   # 检测 443 端口
https://github.com            # 支持直接贴 URL（自动滤掉 https://）
my-site.local:8443/api/status # 支持自定义端口且自动滤掉后缀路径
# 我是整行注释
EOF
```

> [!TIP]
> **配置文件域名解析规则**：
> 1. **支持自定义端口**：格式为 `域名:端口`（例如 `example.com:8443`），工具会自动抓取指定端口进行 SSL 握手与到期检测；若未填端口，则默认使用 `443`。
> 2. **自动去除协议头和后缀路径**：如果您输入了完整的 URL（例如 `https://github.com/path/to/page`），脚本会自动剥离并识别为 `github.com`；如果带端口（如 `https://my-site.local:8443/api`），则自动识别为 `my-site.local:8443`。
> 3. **支持注释管理**：支持以 `#` 形式在行尾添加行内备注，或者单独成行作为整行注释，方便记录域名用途。

### 2. 生产环境部署 (推荐)
挂载整个配置目录，脚本会自动在其中创建并管理状态文件。

```bash
docker run -d \
  --name ssl-monitor \
  --restart always \
  -v $(pwd)/conf:/app/conf \
  -e TZ=Asia/Shanghai \
  -e DINGTALK_TOKEN="您的钉钉Token" \
  -e DINGTALK_SECRET="您的加签Secret(可选)" \
  -e DINGTALK_KEYWORD="您的关键词(可选)" \
  -e ALERT_INFO_DAYS="14" \
  -e ALERT_WARNING_DAYS="7" \
  -e ALERT_CRITICAL_DAYS="3" \
  carman5012/ssl-monitor:v1.0.0
```

### 3. 测试模式 (立即执行且退出)
增加 `-e TEST_MODE=true`，脚本将立即巡检，发送带有 `[TEST]` 标记的通知（不影响生产状态记录）并退出。可以使用 `--rm` 方便地测试您的配置（如邮箱或钉钉的关键词、签名等）：

```bash
docker run --rm \
  -v $(pwd)/conf:/app/conf \
  -e TZ=Asia/Shanghai \
  -e TEST_MODE=true \
  -e DINGTALK_TOKEN="您的钉钉Token" \
  -e DINGTALK_SECRET="您的加签Secret(可选)" \
  -e DINGTALK_KEYWORD="您的关键词(可选)" \
  carman5012/ssl-monitor:latest
```

---

## ⚙️ 环境变量说明

| 变量名 | 是否必填 | 默认值 | 说明 |
| :--- | :---: | :--- | :--- |
| `LIST_FILE` | 否 | `websites_list.txt` | 域名列表文件名，若只给名称则自动在挂载目录下找 |
| `STATE_FILE` | 否 | `ssl_alert_state.json`| 状态记录文件名，自动在挂载目录下管理 |
| `DINGTALK_TOKEN`  | 否 | - | 钉钉机器人的 Access Token（与 `DINGTALK_WEBHOOK` 二选一，推荐） |
| `DINGTALK_WEBHOOK`| 否 | - | 钉钉机器人的 Webhook 完整地址（兼容只填写 Access Token 模式） |
| `DINGTALK_SECRET` | 否 | - | 钉钉机器人安全设置中的**加签密钥**（开启后自动计算签名） |
| `DINGTALK_KEYWORD`| 否 | - | 钉钉机器人安全设置中的**自定义关键词**（开启后自动追加到消息内容中） |
| `SMTP_HOST` | 否 | - | SMTP 服务器地址 |
| `SMTP_USER` | 否 | - | 发信邮箱账号 |
| `SMTP_PASS` | 否 | - | 邮箱授权码/密码 |
| `EMAIL_TO` | 否 | - | 收件人邮箱，多个用逗号分隔 |
| `TEST_MODE` | 否 | `false` | 设置为 `true` 开启测试模式，强制告警不写状态 |
| `ALERT_INFO_DAYS` | 否 | `14` | 提醒告警阈值（天数，少于或等于该值触发提醒） |
| `ALERT_WARNING_DAYS` | 否 | `7` | 警告告警阈值（天数，少于或等于该值触发警告） |
| `ALERT_CRITICAL_DAYS`| 否 | `3` | 严重告警阈值（天数，少于或等于该值触发严重） |
| `TZ` | 否 | `Asia/Shanghai` | 时区设置，强烈建议设为北京时间 |

---

## 🔔 告警逻辑说明

1.  **动态告警阶梯：**
    可通过配置 `ALERT_INFO_DAYS`、`ALERT_WARNING_DAYS` 和 `ALERT_CRITICAL_DAYS` 环境变量自定义三个告警等级（提醒、警告、严重）的剩余天数阈值。
2.  **何时发消息？**
    *   域名的剩余天数进入了新的阶梯（例如从 `ALERT_INFO_DAYS` 外降到阈值内，或从 `ALERT_WARNING_DAYS` 降到 `ALERT_CRITICAL_DAYS`）。
    *   该域名目前处于告警状态，且今天是节假日结束后的第一个工作日。
3.  **何时不发消息？**
    *   域名状态稳定，剩余天数虽在减少但未跨越阶梯。
    *   域名已经恢复正常。
4.  **节假日判断：**
    *   默认请求 `timor.tech` API。若 API 离线，自动回退到常规周一至周五工作日逻辑，确保高可用。

---

## 📄 状态文件示例 (`ssl_alert_state.json`)
```json
{
    "example.com": {
        "level": "警告",
        "is_holiday": false,
        "alert_time": "2026-05-14 09:12:45"
    }
}
```
通过该文件，您可以随时审计每个域名的最后告警状态。
