<template>
  <div class="auth-overlay" :class="{ show: show }">
    <div class="auth-card">
      <div class="auth-logo-icon">
        <ShieldCheck style="width: 24px; height: 24px;" />
      </div>
      <h2 class="auth-title">{{ isInitialized ? '系统登录' : '创建管理员账号' }}</h2>
      <p class="auth-desc">
        {{ isInitialized ? '请输入管理员凭证以访问控制台' : '检测到系统首次运行，请设置您的初始管理员账号和密码' }}
      </p>
      
      <div class="input-wrapper" style="margin-bottom:16px;">
        <User class="input-icon" style="width: 16px; height: 16px;" />
        <input 
          type="text" 
          v-model="username" 
          class="input-field" 
          placeholder="管理员用户名"
          @keyup.enter="submit"
        >
      </div>
      <div class="input-wrapper password-container" style="margin-bottom:24px;">
        <Lock class="input-icon" style="width: 16px; height: 16px;" />
        <input 
          :type="showPassword ? 'text' : 'password'" 
          v-model="password" 
          class="input-field" 
          placeholder="密码"
          @keyup.enter="submit"
        >
        <button class="eye-btn" type="button" @click="showPassword = !showPassword">
          <component :is="showPassword ? EyeOff : Eye" style="width: 14px; height: 14px;" />
        </button>
      </div>
      
      <button class="btn btn-primary" style="width: 100%;" :disabled="loading" @click="submit">
        <span>{{ loading ? (isInitialized ? '正在登录...' : '正在创建...') : (isInitialized ? '立即登录' : '完成注册') }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, inject } from 'vue'
import { ShieldCheck, User, Lock, Eye, EyeOff } from 'lucide-vue-next'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  isInitialized: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['auth-success'])

const showToast = inject('showToast')

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)

watch(() => props.show, (newVal) => {
  if (newVal) {
    username.value = ''
    password.value = ''
    showPassword.value = false
  }
})

const submit = async () => {
  const userVal = username.value.trim()
  const passVal = password.value
  
  if (!userVal || !passVal) {
    showToast("用户名和密码不能为空", "error")
    return
  }

  loading.value = true
  const url = props.isInitialized ? "/api/auth/login" : "/api/auth/register"

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: userVal, password: passVal })
    })
    const data = await res.json()

    if (res.ok) {
      if (!props.isInitialized) {
        showToast("管理员账号创建成功，请登录")
        emit('auth-success', false) // 注册成功，去登录
      } else {
        showToast("登录验证成功")
        emit('auth-success', true) // 登录成功
      }
    } else {
      showToast(data.error || "验证失败", "error")
    }
  } catch (e) {
    showToast("请求失败，网络异常", "error")
  } finally {
    loading.value = false
  }
}
</script>
