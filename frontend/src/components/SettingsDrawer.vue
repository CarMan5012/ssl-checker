<template>
  <div class="drawer-overlay" :class="{ show: show }" @click="close">
    <div class="drawer" @click.stop>
      <div class="drawer-header">
        <span class="drawer-title">配置中心</span>
        <button class="btn btn-secondary btn-icon-only" @click="close" style="width:30px; height:30px; border-radius:6px;">
          <X style="width:14px; height:14px;" />
        </button>
      </div>
      <div class="drawer-body">
        <form @submit.prevent>
          <!-- 钉钉告警 -->
          <div class="setting-section">
            <div class="setting-section-title">
              <Bell style="width: 14px; height: 14px;" />
              <span>钉钉机器人告警</span>
            </div>
            <div class="form-group">
              <label class="form-label">Webhook 地址 / Access Token</label>
              <input 
                type="text" 
                v-model="form.dingtalk_webhook" 
                :class="['input-field', { 'is-error': errors.dingtalk_webhook }]" 
                style="padding-left:12px;" 
                placeholder="支持粘贴完整 Webhook 链接或 Token"
                @input="clearError('dingtalk_webhook')"
              >
              <div class="field-error-msg" :class="{ show: errors.dingtalk_webhook }">
                <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                <span>{{ errors.dingtalk_webhook }}</span>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">加签密钥 Secret (可选)</label>
              <div class="password-container">
                <input 
                  :type="showSecret.dingtalk ? 'text' : 'password'" 
                  v-model="form.dingtalk_secret" 
                  class="input-field" 
                  style="padding-left:12px;" 
                  placeholder="配置后将自动计算加签签名"
                >
                <button class="eye-btn" type="button" @click="showSecret.dingtalk = !showSecret.dingtalk">
                  <EyeOff v-if="showSecret.dingtalk" style="width: 14px; height: 14px;" />
                  <Eye v-else style="width: 14px; height: 14px;" />
                </button>
              </div>
            </div>
            <div class="form-group" style="margin-bottom: 8px;">
              <label class="form-label">自定义关键词 Keyword (可选)</label>
              <input 
                type="text" 
                v-model="form.dingtalk_keyword" 
                class="input-field" 
                style="padding-left:12px;" 
                placeholder="机器人安全选项里设置的自定义字符"
              >
            </div>
            <button 
              class="btn btn-secondary" 
              type="button" 
              :disabled="testDingtalkLoading" 
              @click="testDingtalk" 
              style="width: 100%; font-size: 12px; height: 32px; padding: 0;"
            >
              <Loader v-if="testDingtalkLoading" class="spin" style="width: 12px; height: 12px; margin-right: 4px;" />
              <Send v-else style="width: 12px; height: 12px; margin-right: 4px;" />
              {{ testDingtalkLoading ? '测试中...' : '测试钉钉发送' }}
            </button>
          </div>

          <!-- 邮件告警 -->
          <div class="setting-section">
            <div class="setting-section-title">
              <Mail style="width: 14px; height: 14px;" />
              <span>发信 SMTP 邮箱</span>
            </div>
            <div style="display:grid; grid-template-columns: 2fr 1fr; gap:10px;" class="form-group">
              <div>
                <label class="form-label">SMTP 服务器主机</label>
                <input 
                  type="text" 
                  v-model="form.smtp_host" 
                  :class="['input-field', { 'is-error': errors.smtp_host }]" 
                  style="padding-left:12px;" 
                  placeholder="如 smtp.qq.com"
                  @input="clearError('smtp_host')"
                >
                <div class="field-error-msg" :class="{ show: errors.smtp_host }">
                  <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                  <span>{{ errors.smtp_host }}</span>
                </div>
              </div>
              <div>
                <label class="form-label">端口</label>
                <input 
                  type="number" 
                  v-model.number="form.smtp_port" 
                  :class="['input-field', { 'is-error': errors.smtp_port }]" 
                  style="padding-left:12px;" 
                  placeholder="465" 
                  min="1" 
                  max="65535"
                  @input="clearError('smtp_port')"
                >
                <div class="field-error-msg" :class="{ show: errors.smtp_port }">
                  <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                  <span>{{ errors.smtp_port }}</span>
                </div>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">发信账号 (邮箱账号)</label>
              <input 
                type="text" 
                v-model="form.smtp_user" 
                :class="['input-field', { 'is-error': errors.smtp_user }]" 
                style="padding-left:12px;" 
                placeholder="如 user@qq.com"
                @input="clearError('smtp_user')"
              >
              <div class="field-error-msg" :class="{ show: errors.smtp_user }">
                <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                <span>{{ errors.smtp_user }}</span>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">邮箱授权密码/口令</label>
              <div class="password-container">
                <input 
                  :type="showSecret.smtp ? 'text' : 'password'" 
                  v-model="form.smtp_pass" 
                  class="input-field" 
                  style="padding-left:12px;" 
                  placeholder="SMTP 授权码（不填保留原密码）"
                >
                <button class="eye-btn" type="button" @click="showSecret.smtp = !showSecret.smtp">
                  <EyeOff v-if="showSecret.smtp" style="width: 14px; height: 14px;" />
                  <Eye v-else style="width: 14px; height: 14px;" />
                </button>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">收件人邮箱 (多个以英文逗号分隔)</label>
              <input 
                type="text" 
                v-model="form.email_to" 
                :class="['input-field', { 'is-error': errors.email_to }]" 
                style="padding-left:12px;" 
                placeholder="收信箱列表"
                @input="clearError('email_to')"
              >
              <div class="field-error-msg" :class="{ show: errors.email_to }">
                <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                <span>{{ errors.email_to }}</span>
              </div>
            </div>
            <button 
              class="btn btn-secondary" 
              type="button" 
              :disabled="testEmailLoading" 
              @click="testEmail" 
              style="width: 100%; font-size: 12px; height: 32px; padding: 0;"
            >
              <Loader v-if="testEmailLoading" class="spin" style="width: 12px; height: 12px; margin-right: 4px;" />
              <MailIcon v-else style="width: 12px; height: 12px; margin-right: 4px;" />
              {{ testEmailLoading ? '测试中...' : '测试邮件发送' }}
            </button>
          </div>

          <!-- 告警天数阈值 -->
          <div class="setting-section">
            <div class="setting-section-title">
              <Sliders style="width: 14px; height: 14px;" />
              <span>告警天数阈值</span>
            </div>
            <div class="form-row">
              <div>
                <label class="form-label">提醒天数</label>
                <input 
                  type="number" 
                  v-model.number="form.alert_info_days" 
                  :class="['input-field', { 'is-error': errors.alert_info_days }]" 
                  style="padding-left:12px;" 
                  min="1" 
                  max="365"
                  @input="clearError('alert_info_days')"
                >
                <div class="field-error-msg" :class="{ show: errors.alert_info_days }">
                  <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                  <span>{{ errors.alert_info_days }}</span>
                </div>
              </div>
              <div>
                <label class="form-label">警告天数</label>
                <input 
                  type="number" 
                  v-model.number="form.alert_warning_days" 
                  :class="['input-field', { 'is-error': errors.alert_warning_days }]" 
                  style="padding-left:12px;" 
                  min="1" 
                  max="365"
                  @input="clearError('alert_warning_days')"
                >
                <div class="field-error-msg" :class="{ show: errors.alert_warning_days }">
                  <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                  <span>{{ errors.alert_warning_days }}</span>
                </div>
              </div>
              <div>
                <label class="form-label">严重天数</label>
                <input 
                  type="number" 
                  v-model.number="form.alert_critical_days" 
                  :class="['input-field', { 'is-error': errors.alert_critical_days }]" 
                  style="padding-left:12px;" 
                  min="1" 
                  max="365"
                  @input="clearError('alert_critical_days')"
                >
                <div class="field-error-msg" :class="{ show: errors.alert_critical_days }">
                  <AlertCircle style="width:11px;height:11px;flex-shrink:0;" />
                  <span>{{ errors.alert_critical_days }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 通用配置 -->
          <div class="setting-section">
            <div class="setting-section-title">
              <Cog style="width: 14px; height: 14px;" />
              <span>通用选项</span>
            </div>
            <div class="form-group" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;">
              <label class="form-label" style="margin-bottom: 0; cursor: pointer;" for="cfg_alert_use_emoji">内置模板启用表情图标</label>
              <input type="checkbox" id="cfg_alert_use_emoji" v-model="form.alert_use_emoji" style="width: 18px; height: 18px; cursor: pointer;">
            </div>
          </div>
        </form>
      </div>
      <div class="drawer-footer">
        <button class="btn btn-secondary" @click="$emit('logout')" style="margin-right:auto; color:var(--danger-color); border-color:var(--danger-color); background:transparent;">
          <LogOut style="width:14px; height:14px;" />
          <span>注销退出</span>
        </button>
        <button class="btn btn-secondary" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="saveLoading" @click="saveSettings">
          {{ saveLoading ? '保存中...' : '保存配置' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, inject } from 'vue'
import { 
  X, Bell, AlertCircle, Eye, EyeOff, Send, Mail, Mail as MailIcon, Sliders, Cog, LogOut, Loader 
} from 'lucide-vue-next'
import { apiFetch } from '../utils/api'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'logout', 'saved'])

const showToast = inject('showToast')
const triggerOnUnauthorized = inject('triggerOnUnauthorized')

const originalSettings = ref(null)
const saveLoading = ref(false)
const testDingtalkLoading = ref(false)
const testEmailLoading = ref(false)

const showSecret = reactive({
  dingtalk: false,
  smtp: false
})

const form = reactive({
  dingtalk_webhook: '',
  dingtalk_secret: '',
  dingtalk_keyword: '',
  smtp_host: '',
  smtp_port: 465,
  smtp_user: '',
  smtp_pass: '',
  email_to: '',
  alert_info_days: 14,
  alert_warning_days: 7,
  alert_critical_days: 3,
  alert_use_emoji: false
})

const errors = reactive({
  dingtalk_webhook: '',
  smtp_host: '',
  smtp_port: '',
  smtp_user: '',
  email_to: '',
  alert_info_days: '',
  alert_warning_days: '',
  alert_critical_days: ''
})

const clearError = (field) => {
  errors[field] = ''
}

const loadSettings = async () => {
  try {
    const res = await apiFetch("/api/settings", {}, triggerOnUnauthorized)
    if (!res) return
    const data = await res.json()
    originalSettings.value = JSON.parse(JSON.stringify(data))
    
    form.dingtalk_webhook = data.dingtalk_webhook || ''
    form.dingtalk_secret = data.dingtalk_secret || ''
    form.dingtalk_keyword = data.dingtalk_keyword || ''
    form.smtp_host = data.smtp_host || ''
    form.smtp_port = data.smtp_port || 465
    form.smtp_user = data.smtp_user || ''
    form.smtp_pass = data.smtp_pass || ''
    form.email_to = data.email_to || ''
    form.alert_info_days = data.alert_info_days || 14
    form.alert_warning_days = data.alert_warning_days || 7
    form.alert_critical_days = data.alert_critical_days || 3
    form.alert_use_emoji = data.alert_use_emoji || false
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("加载系统配置失败", "error")
    }
  }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    // 重置状态
    showSecret.dingtalk = false
    showSecret.smtp = false
    Object.keys(errors).forEach(k => errors[k] = '')
    loadSettings()
  }
})

const close = () => {
  emit('close')
}

const validate = () => {
  Object.keys(errors).forEach(k => errors[k] = '')
  let valid = true
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

  // 钉钉 Webhook 校验
  if (form.dingtalk_webhook) {
    const isUrl = /^https?:\/\/.+/.test(form.dingtalk_webhook)
    const isToken = /^[A-Za-z0-9\-_]{20,}$/.test(form.dingtalk_webhook)
    if (!isUrl && !isToken) {
      errors.dingtalk_webhook = '请填写完整的 Webhook URL (https://...) 或有效的 Access Token'
      valid = false
    }
  }

  // SMTP 校验（若填了 SMTP 主机，则其余部分强制必填）
  if (form.smtp_host) {
    if (!form.smtp_port) {
      errors.smtp_port = '端口不能为空'
      valid = false
    } else {
      const port = parseInt(form.smtp_port)
      if (isNaN(port) || port < 1 || port > 65535) {
        errors.smtp_port = '端口范围应在 1 ~ 65535 之间'
        valid = false
      }
    }
    if (!form.smtp_user) {
      errors.smtp_user = '发信账号不能为空'
      valid = false
    } else if (!emailRegex.test(form.smtp_user)) {
      errors.smtp_user = '请输入有效的邮箱地址'
      valid = false
    }
    if (!form.email_to) {
      errors.email_to = '收件人邮箱不能为空'
      valid = false
    } else {
      const recipients = form.email_to.split(',').map(s => s.trim()).filter(Boolean)
      const invalidAddr = recipients.find(addr => !emailRegex.test(addr))
      if (invalidAddr) {
        errors.email_to = `"${invalidAddr}" 不是有效的邮箱地址`
        valid = false
      }
    }
  } else {
    // 未填主机，只做选填的格式校验
    if (form.smtp_port) {
      const port = parseInt(form.smtp_port)
      if (isNaN(port) || port < 1 || port > 65535) {
        errors.smtp_port = '端口范围应在 1 ~ 65535 之间'
        valid = false
      }
    }
    if (form.smtp_user && !emailRegex.test(form.smtp_user)) {
      errors.smtp_user = '请输入有效的邮箱地址'
      valid = false
    }
    if (form.email_to) {
      const recipients = form.email_to.split(',').map(s => s.trim()).filter(Boolean)
      const invalidAddr = recipients.find(addr => !emailRegex.test(addr))
      if (invalidAddr) {
        errors.email_to = `"${invalidAddr}" 不是有效的邮箱地址`
        valid = false
      }
    }
  }

  // 告警天数校验
  const info = parseInt(form.alert_info_days)
  const warn = parseInt(form.alert_warning_days)
  const crit = parseInt(form.alert_critical_days)

  if (isNaN(info) || info < 1 || info > 365) {
    errors.alert_info_days = '提醒天数应为 1 ~ 365 的正整数'
    valid = false
  }
  if (isNaN(warn) || warn < 1 || warn > 365) {
    errors.alert_warning_days = '警告天数应为 1 ~ 365 的正整数'
    valid = false
  }
  if (isNaN(crit) || crit < 1 || crit > 365) {
    errors.alert_critical_days = '严重天数应为 1 ~ 365 的正整数'
    valid = false
  }

  if (valid && !(crit < warn && warn < info)) {
    const msg = '天数阈值需满足：严重 < 警告 < 提醒'
    errors.alert_info_days = msg
    errors.alert_warning_days = msg
    errors.alert_critical_days = msg
    valid = false
  }

  return valid
}

const saveSettings = async () => {
  if (!validate()) {
    showToast('请检查并修正表单中的错误项', 'error')
    return
  }

  saveLoading.value = true
  const payload = {
    dingtalk_webhook: form.dingtalk_webhook.trim(),
    dingtalk_secret: form.dingtalk_secret,
    dingtalk_keyword: form.dingtalk_keyword.trim(),
    smtp_host: form.smtp_host.trim(),
    smtp_port: parseInt(form.smtp_port) || 465,
    smtp_user: form.smtp_user.trim(),
    smtp_pass: form.smtp_pass,
    email_to: form.email_to.trim(),
    alert_info_days: parseInt(form.alert_info_days) || 14,
    alert_warning_days: parseInt(form.alert_warning_days) || 7,
    alert_critical_days: parseInt(form.alert_critical_days) || 3,
    alert_use_emoji: form.alert_use_emoji
  }

  let changedModules = []
  if (originalSettings.value) {
    if (
      payload.dingtalk_webhook !== originalSettings.value.dingtalk_webhook ||
      payload.dingtalk_secret !== originalSettings.value.dingtalk_secret ||
      payload.dingtalk_keyword !== originalSettings.value.dingtalk_keyword
    ) {
      changedModules.push("钉钉告警")
    }
    
    if (
      payload.smtp_host !== originalSettings.value.smtp_host ||
      payload.smtp_port !== originalSettings.value.smtp_port ||
      payload.smtp_user !== originalSettings.value.smtp_user ||
      payload.smtp_pass !== originalSettings.value.smtp_pass ||
      payload.email_to !== originalSettings.value.email_to
    ) {
      changedModules.push("邮件告警")
    }
    
    if (
      payload.alert_info_days !== originalSettings.value.alert_info_days ||
      payload.alert_warning_days !== originalSettings.value.alert_warning_days ||
      payload.alert_critical_days !== originalSettings.value.alert_critical_days
    ) {
      changedModules.push("告警天数")
    }
    
    if (payload.alert_use_emoji !== originalSettings.value.alert_use_emoji) {
      changedModules.push("表情配置")
    }
  }

  try {
    const res = await apiFetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }, triggerOnUnauthorized)
    if (!res) return

    const data = await res.json()
    if (res.ok) {
      if (changedModules.length === 0) {
        showToast("配置保存成功 (未发生内容修改)", "info")
      } else {
        showToast(`${changedModules.join("、")}配置保存成功`)
      }
      emit('saved', changedModules.includes("告警天数"))
      close()
    } else {
      showToast(data.error || "保存失败", "error")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("保存异常", "error")
    }
  } finally {
    saveLoading.value = false
  }
}

const testDingtalk = async () => {
  if (!form.dingtalk_webhook) {
    showToast("请先输入 Webhook 地址！", "error")
    return
  }

  testDingtalkLoading.value = true
  try {
    const res = await apiFetch("/api/settings/test/dingtalk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dingtalk_webhook: form.dingtalk_webhook.trim(),
        dingtalk_secret: form.dingtalk_secret,
        dingtalk_keyword: form.dingtalk_keyword.trim(),
        alert_use_emoji: form.alert_use_emoji
      })
    }, triggerOnUnauthorized)
    if (!res) return

    const data = await res.json()
    if (res.ok) {
      showToast("钉钉测试消息发送成功，请在群聊中确认！")
    } else {
      showToast(`测试失败: ${data.error}`, "error")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("请求异常，请检查网络", "error")
    }
  } finally {
    testDingtalkLoading.value = false
  }
}

const testEmail = async () => {
  if (!form.smtp_host || !form.smtp_port || !form.smtp_user || !form.email_to) {
    showToast("请先完整填写 SMTP 服务器、端口、账号和收件人！", "error")
    return
  }

  testEmailLoading.value = true
  try {
    const res = await apiFetch("/api/settings/test/email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        smtp_host: form.smtp_host.trim(),
        smtp_port: parseInt(form.smtp_port) || 465,
        smtp_user: form.smtp_user.trim(),
        smtp_pass: form.smtp_pass,
        email_to: form.email_to.trim(),
        alert_use_emoji: form.alert_use_emoji
      })
    }, triggerOnUnauthorized)
    if (!res) return

    const data = await res.json()
    if (res.ok) {
      showToast("邮件测试发送成功，请查收邮箱！")
    } else {
      showToast(`测试失败: ${data.error}`, "error")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("请求异常，请检查网络", "error")
    }
  } finally {
    testEmailLoading.value = false
  }
}
</script>
