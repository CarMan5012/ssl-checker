# 🛡️ SSL-Monitor: 专业级证书到期监控告警工具

`SSL-Monitor` 是一款轻量级、智能化的 SSL 证书到期巡检工具。它通过三级告警策略和状态追踪机制，确保您在证书过期前获得及时的提醒，同时通过“告警升级”逻辑彻底杜绝重复消息轰炸。

## ✨ 核心特性

-   **智能三级策略**：硬编码阶梯阈值（14天提醒、7天警告、3天严重），逻辑清晰。
-   **防消息风暴**：引入状态持久化机制，**只有当告警等级提升（如从“提醒”变为“警告”）时才会触发通知**。
-   **随机巡检时间**：生产模式下，每天上午 `09:00 - 09:59` 之间随机选择一分钟执行，避免定时任务过于机械。
-   **双通道告警**：支持 **SMTP 邮件**（HTML 表格）和 **钉钉群机器人**（Markdown 消息）。
-   **一键测试模式**：支持 `--test` 参数，快速验证配置并强制发送全量通知，运行后自动退出。
-   **Docker 化部署**：支持环境变量配置，开箱即用。

---

## 🚀 快速开始 (Docker)

镜像已托管至 Docker Hub: `carman5012/ssl-monitor`

### 1. 准备域名列表
创建一个 `websites_list.txt` 文件，每行一个域名（可带端口）：
```text
example.com
google.com:443
# 我是注释
my-internal-site.local:8443
```

### 2. 生产环境部署 (推荐)
挂载状态文件 `ssl_alert_state.json` 以确保重启后不会重复告警。

```bash
docker run -d \
  --name ssl-monitor \
  --restart always \
  -v $(pwd)/websites_list.txt:/app/websites_list.txt \
  -v $(pwd)/ssl_alert_state.json:/app/ssl_alert_state.json \
  -e LIST_FILE=/app/websites_list.txt \
  -e SMTP_HOST="smtp.exmail.qq.com" \
  -e SMTP_PORT=465 \
  -e SMTP_USER="your-email@example.com" \
  -e SMTP_PASS="your-app-password" \
  -e EMAIL_TO="receiver@example.com" \
  -e DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx" \
  -e TZ=Asia/Shanghai \
  carman5012/ssl-monitor:latest
```

### 3. 测试模式 (立即执行)
只需增加 `-e TEST_MODE=true`，脚本将立即巡检所有域名，发送带有 `[TEST]` 标记的消息后自动销毁容器。

```bash
docker run --rm \
  -v $(pwd)/websites_list.txt:/app/websites_list.txt \
  -e TEST_MODE=true \
  -e DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx" \
  carman5012/ssl-monitor:latest
```

---

## ⚙️ 环境变量说明

| 变量名 | 是否必填 | 默认值 | 说明 |
| :--- | :---: | :--- | :--- |
| `LIST_FILE` | 否 | `websites_list.txt` | 存放待检测域名的文件路径 |
| `SMTP_HOST` | 否 | - | SMTP 服务器地址 (如 `smtp.gmail.com`) |
| `SMTP_PORT` | 否 | `465` | SMTP 端口 (通常 465 为 SSL, 587 为 STARTTLS) |
| `SMTP_USER` | 否 | - | 发信邮箱账号 |
| `SMTP_PASS` | 否 | - | 邮箱授权码/密码 |
| `EMAIL_TO` | 否 | - | 收件人邮箱，多个用逗号分隔 |
| `DINGTALK_WEBHOOK`| 否 | - | 钉钉机器人的 Webhook 完整地址 |
| `TEST_MODE` | 否 | `false` | 设置为 `true` 开启测试模式，强制告警并退出 |
| `TZ` | 否 | `UTC` | 时区设置，建议设为 `Asia/Shanghai` |

---

## 🔔 告警通道配置建议

脚本支持多种运行模式，您可以根据需要灵活配置：

-   **全功能模式**：同时配置 `SMTP` 和 `DINGTALK`，实现双路告警备份。
-   **单通道模式**：建议**只配置一种**（如仅配置钉钉），脚本会自动识别并仅通过该通道发送消息。
-   **纯日志模式**：如果您不配置任何告警环境变量，脚本依然会**正常运行并巡检**，您可以通过 `docker logs -f ssl-monitor` 实时查看巡检结果和证书状态。
-   **测试模式**：在启动时增加 `-e TEST_MODE=true`，可以立即触发一次全量巡检并输出结果。

---

## 🛠️ 告警逻辑细节

### 三级告警定义
-   **提醒 (Notice)**: 剩余天数 `≤ 14` 天。
-   **警告 (Warning)**: 剩余天数 `≤ 7` 天。
-   **严重 (Critical)**: 剩余天数 `≤ 3` 天 或 证书获取失败。

### 为什么我没收到通知？
本工具设计了**状态升级触发**逻辑：
-   如果昨天是 13 天（提醒），今天是 12 天（提醒），由于等级没变，**不会**重复发通知。
-   如果昨天是 8 天（提醒），今天降到了 7 天（警告），由于等级从“提醒”升级到了“警告”，**会**立即发送新通知。
-   如果证书已过期或读取失败，将始终标记为“严重”。

---

## 📂 本地开发

1.  克隆代码并进入目录。
2.  安装依赖：
    ```bash
    pip install cryptography requests schedule
    ```
3.  运行：
    ```bash
    python ssl_check.py
    ```

---

## 📄 开源协议
[MIT License](LICENSE)

---

** carman5012/ssl-monitor **
*让证书管理更省心，告别手动巡检。*
