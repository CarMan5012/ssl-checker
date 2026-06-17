# 🛡️ SSL-Checker: 证书到期巡检告警工具

`SSL-Checker` 是一款轻量化 SSL 证书巡检工具。支持 **Web 可视化管理控制台**，内置密码登录、配置热保存、域名批量粘贴导入、防消息风暴、节假日智能补发等特性。

---

## ✨ 核心特性

- **可视化配置中心**：支持在网页端配置 SMTP 发信邮箱、钉钉机器人以及告警天数阈值，实时生效，无需重启容器。
- **多用户安全认证**：基于 Cookie-Session 的密码登录验证，首次运行无用户时自动引导创建管理员账号。
- **完美兼容 IPv6**：支持带方括号的 IPv6 地址与端口（如 `[2001:db8::1]:8443`），前端校验与检测底层完全适配。
- **批量域名管理**：支持域名和端口一键批量粘贴导入，自动清洗并过滤重复项；提供单个域名局部实时刷新能力。
- **防告警消息风暴**：本地保存告警状态，仅当风险等级提升（提醒/警告/严重/失败）或假期后首个工作日才触发发送。
- **智能节假日补发**：自动感知国家法定节假日，非工作日期间的低级告警将顺延至节后首个工作日早上补发。
- **每日随机选点巡检**：定时循环任务在每天上午 `09:00 - 09:59` 之间随机时间启动，模拟人工巡检节奏。

---

## 🚀 快速开始 (Docker)

### 1. 准备配置目录
在宿主机创建配置目录，并放入域名列表文件 `websites_list.txt`（若无此文件，启动后会自动创建）：
```bash
mkdir -p ./conf
cat <<EOF > ./conf/websites_list.txt
# 每一行填写一个域名，支持端口与行内注释
example.com                   # 默认 443 端口
https://github.com            # 协议前缀与尾部路径会自动剥离
[2001:db8::1]:8443            # 支持 IPv6 域名与解析
EOF
```

### 2. 部署运行
挂载宿主机配置目录并映射 `8080` 端口启动：
```bash
docker run -d \
  --name ssl-checker \
  --restart always \
  -p 8080:8080 \
  -v $(pwd)/conf:/app/conf \
  -e TZ=Asia/Shanghai \
  carman5012/ssl-checker:latest
```
> [!NOTE]
> 容器启动后，在浏览器访问 `http://IP:8080` 进入控制台，直接在“配置中心”通过可视化界面填写发信邮箱与钉钉机器人等，保存后实时热重载，无需配置繁琐的命令行环境变量。

### 3. 一键测试
使用 `TEST_MODE=true` 环境变量即可立即触发一次巡检并发送 `[TEST]` 告警测试：
```bash
docker run --rm \
  -v $(pwd)/conf:/app/conf \
  -e TZ=Asia/Shanghai \
  -e TEST_MODE=true \
  -e DINGTALK_TOKEN="您的钉钉Token" \
  carman5012/ssl-checker:latest
```

---

## ⚙️ 环境变量说明

| 环境变量名 | 是否必填 | 默认值 | 说明 |
| :--- | :---: | :--- | :--- |
| `LIST_FILE` | 否 | `websites_list.txt` | 域名列表文件名，默认从挂载目录下读取 |
| `STATE_FILE` | 否 | `ssl_alert_state.json`| 状态记录文件名，在挂载目录下生成 |
| `DINGTALK_TOKEN`  | 否 | - | 钉钉机器人的 Access Token（与 Webhook 二选一） |
| `DINGTALK_WEBHOOK`| 否 | - | 钉钉机器人的 Webhook 完整地址 |
| `DINGTALK_SECRET` | 否 | - | 钉钉加签密钥 |
| `DINGTALK_KEYWORD`| 否 | - | 钉钉自定义匹配关键词 |
| `SMTP_HOST` | 否 | - | SMTP 服务器地址 |
| `SMTP_PORT` | 否 | `465` | SMTP 服务器端口（默认使用 SSL） |
| `SMTP_USER` | 否 | - | 发信邮箱账号 |
| `SMTP_PASS` | 否 | - | 邮箱授权码/密码 |
| `EMAIL_TO` | 否 | - | 收件人邮箱，多个用逗号分隔 |
| `TEST_MODE` | 否 | `false` | 设置为 `true` 开启单次测试模式，运行后立即退出 |
| `ALERT_INFO_DAYS` | 否 | `14` | 提醒告警天数阈值 |
| `ALERT_WARNING_DAYS` | 否 | `7` | 警告告警天数阈值 |
| `ALERT_CRITICAL_DAYS`| 否 | `3` | 严重告警天数阈值 |
| `TZ` | 否 | `Asia/Shanghai` | 时区设置 |
| `WEB_PORT` | 否 | `8080` | 前端 Web 管理端启动时的监听端口 |

---

## 🔔 告警逻辑说明

1. **动态告警阶梯**：根据 `ALERT_INFO_DAYS` / `ALERT_WARNING_DAYS` / `ALERT_CRITICAL_DAYS` 划分提醒、警告、严重三个告警等级。
2. **何时发消息**：
   - 域名的剩余天数进入了新的阶梯（如从未触发降到提醒值内，或从警告降到严重值内）。
   - 该域名处于告警状态，且今天是节假日结束后的第一个工作日（工作日补发）。
3. **何时不发消息**：状态稳定，剩余天数虽在减少但未跨越阶梯；域名已恢复正常。
4. **状态文件审计**：告警状态安全地保存在挂载目录的 `ssl_alert_state.json` 中，随时可追踪当前预警详情。
