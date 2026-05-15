
docker run -d `
  --name ssl-monitor `
  --restart always `
  -v d:/UserData/AURA/ssl-checker/conf:/app/conf `
  -e TZ=Asia/Shanghai `
  -e DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=979f17a5364bc75b46ad85dc64f35b19f3fbbcdd665d630a999c6cc2f2b612e6" `
  carman5012/ssl-monitor:v1.0.0






  docker run --rm `
  -v d:/UserData/AURA/ssl-checker/websites_list.txt:/app/websites_list.txt `
  -e TEST_MODE=true `
  -e DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=979f17a5364bc75b46ad85dc64f35b19f3fbbcdd665d630a999c6cc2f2b612e6" `
  carman5012/ssl-monitor:v1.0.0



# docker run -d \
#   --name ssl-monitor \
#   --restart always \
#   -v $(pwd)/websites_list.txt:/app/websites_list.txt \
#   -v $(pwd)/ssl_alert_state.json:/app/ssl_alert_state.json \
#   -e SMTP_HOST="smtp.exmail.qq.com" \
#   -e SMTP_USER="your-email@example.com" \
#   -e SMTP_PASS="your-app-password" \
#   -e EMAIL_TO="receiver@example.com" \
#   -e DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx" \
#   -e TZ=Asia/Shanghai \
#   carman5012/ssl-monitor:latest
