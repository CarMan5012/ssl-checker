<template>
  <div class="container">
    <!-- 头部区域 -->
    <header>
      <div class="logo-area">
        <div class="logo-icon-wrapper">
          <ShieldCheck style="width: 22px; height: 22px;" />
        </div>
        <div>
          <h1>SSL 证书监控看板</h1>
          <p style="font-size: 11px; color: var(--text-secondary); font-weight: 500;">实时证书巡检 · 智能分级告警</p>
        </div>
      </div>

      <!-- 导航链接菜单 -->
      <nav class="nav-menu" :class="{ show: loggedIn }">
        <button 
          class="nav-item" 
          :class="{ active: currentPath === '/dashboard' }" 
          @click="navigate('/dashboard')"
        >
          <BarChart3 style="width: 14px; height: 14px;" />
          <span>监控看板</span>
        </button>
        <button 
          class="nav-item" 
          :class="{ active: currentPath === '/dashboard/domains' }" 
          @click="navigate('/dashboard/domains')"
        >
          <Globe style="width: 14px; height: 14px;" />
          <span>域名管理</span>
        </button>
      </nav>

      <div class="action-group">
        <!-- 管理员登录入口 (未登录时展示) -->
        <button 
          v-if="!loggedIn" 
          class="btn btn-primary" 
          @click="navigate('/login')" 
          title="管理员登录" 
          style="gap: 6px; padding: 8px 16px; font-size: 13px;"
        >
          <LogIn style="width: 14px; height: 14px;" />
          <span>管理员登录</span>
        </button>
        <!-- 检查更新 (全局刷新) -->
        <button 
          v-if="loggedIn" 
          class="btn btn-secondary btn-icon-only" 
          @click="loadDomains(true)" 
          title="检查更新"
          :disabled="domainsLoading"
        >
          <RefreshCw :class="{ spin: domainsLoading }" style="width: 16px; height: 16px;" />
        </button>
        <!-- 主题切换 -->
        <button class="btn btn-secondary btn-icon-only" @click="toggleTheme" title="切换主题">
          <component :is="theme === 'dark' ? Sun : Moon" style="width: 16px; height: 16px;" />
        </button>
        <!-- 告警配置 -->
        <button 
          v-if="loggedIn" 
          class="btn btn-secondary btn-icon-only" 
          @click="navigate('/dashboard/settings')" 
          title="告警配置"
        >
          <Settings style="width: 16px; height: 16px;" />
        </button>
        <!-- 安全退出 -->
        <button 
          v-if="loggedIn" 
          class="btn btn-secondary btn-icon-only" 
          @click="handleLogout" 
          title="注销退出" 
          style="color: var(--danger-color); border-color: rgba(239, 68, 68, 0.15);"
        >
          <LogOut style="width: 16px; height: 16px;" />
        </button>
      </div>
    </header>

    <!-- 看板大屏视图 -->
    <div v-show="currentPath === '/dashboard' || (currentPath === '/dashboard/settings' && lastActivePath === '/dashboard')" class="route-view active">
      <Dashboard :domains="domains" :loading="domainsLoading" />
    </div>

    <!-- 域名管理视图 -->
    <div v-show="currentPath === '/dashboard/domains' || (currentPath === '/dashboard/settings' && lastActivePath === '/dashboard/domains')" class="route-view active">
      <DomainManage 
        :domains="domains" 
        :loading="domainsLoading" 
        @open-import="showImportModal = true"
        @confirm-delete="handleConfirmDelete"
        @refresh="loadDomains(false)"
        @update-domain="handleUpdateDomain"
      />
    </div>

    <!-- 全屏登录/初始化注册锁屏遮罩层 -->
    <AuthOverlay 
      :show="currentPath === '/login'" 
      :is-initialized="isSystemInitialized" 
      @auth-success="handleAuthSuccess"
    />

    <!-- 系统设置侧边抽屉 -->
    <SettingsDrawer 
      :show="currentPath === '/dashboard/settings'" 
      @close="closeSettingsDrawer"
      @logout="handleLogout"
      @saved="onSettingsSaved"
    />

    <!-- 批量导入域名模态框 -->
    <ImportModal 
      :show="showImportModal" 
      @close="showImportModal = false"
      @imported="loadDomains(false)"
    />

    <!-- 删除域名二次确认模态框 -->
    <ConfirmModal 
      :show="!!deleteTarget" 
      :domain="deleteTarget"
      @close="deleteTarget = null"
      @confirmed="loadDomains(false)"
    />

    <!-- Toast 消息容器 -->
    <div class="toast-container" id="toastContainer">
      <div 
        v-for="t in toasts" 
        :key="t.id" 
        :class="['toast', `toast-${t.type}`, { show: t.show }]"
      >
        <component :is="getToastIcon(t.type)" class="toast-icon" />
        <div class="toast-content">
          <div class="toast-message">{{ t.message }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, provide } from 'vue'
import { 
  ShieldCheck, BarChart3, Globe, LogIn, RefreshCw, Moon, Sun, Settings, LogOut,
  CheckCircle, XCircle, Info, AlertCircle 
} from 'lucide-vue-next'

import Dashboard from './components/Dashboard.vue'
import DomainManage from './components/DomainManage.vue'
import AuthOverlay from './components/AuthOverlay.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import ImportModal from './components/ImportModal.vue'
import ConfirmModal from './components/ConfirmModal.vue'

import { apiFetch } from './utils/api'

const currentPath = ref('/dashboard')
const lastActivePath = ref('/dashboard')
const loggedIn = ref(false)
const isSystemInitialized = ref(true)

const domains = ref([])
const domainsLoading = ref(false)
const theme = ref('dark')

const toasts = ref([])
const showImportModal = ref(false)
const deleteTarget = ref(null)

// Toast 气泡逻辑
const showToast = (message, type = 'success') => {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, message, type, show: false })
  setTimeout(() => {
    const t = toasts.value.find(x => x.id === id)
    if (t) t.show = true
  }, 50)

  setTimeout(() => {
    const t = toasts.value.find(x => x.id === id)
    if (t) t.show = false
    setTimeout(() => {
      toasts.value = toasts.value.filter(x => x.id !== id)
    }, 350)
  }, 4000)
}

const getToastIcon = (type) => {
  if (type === 'error') return XCircle
  if (type === 'info') return Info
  return CheckCircle
}

// Interceptor 拦截 401 触发的退出与重置行为
const triggerOnUnauthorized = () => {
  loggedIn.value = false
  navigate('/dashboard')
}

// 依赖注入
provide('showToast', showToast)
provide('triggerOnUnauthorized', triggerOnUnauthorized)

// 主题逻辑
const initTheme = () => {
  const saved = localStorage.getItem('theme')
  theme.value = saved || 'dark'
  applyTheme()
}

const toggleTheme = () => {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
  localStorage.setItem('theme', theme.value)
  applyTheme()
  showToast(`已切换至${theme.value === 'light' ? '明亮' : '暗黑'}模式`, 'info')
}

const applyTheme = () => {
  if (theme.value === 'dark') {
    document.body.classList.add('dark-mode')
  } else {
    document.body.classList.remove('dark-mode')
  }
}

// History 路由器逻辑
const navigate = (path, push = true) => {
  let targetPath = path
  if (targetPath.endsWith('/') && targetPath.length > 1) {
    targetPath = targetPath.slice(0, -1)
  }

  const protectedPaths = ['/dashboard/domains', '/dashboard/settings']

  if (!loggedIn.value) {
    if (targetPath === '/' || targetPath === '') {
      targetPath = '/dashboard'
    } else if (protectedPaths.includes(targetPath)) {
      targetPath = '/login'
    }
  } else {
    if (targetPath === '/login' || targetPath === '/') {
      targetPath = '/dashboard'
    }
  }

  if (push && window.location.pathname !== targetPath) {
    window.history.pushState(null, '', targetPath)
  } else if (!push && window.location.pathname !== targetPath) {
    window.history.replaceState(null, '', targetPath)
  }

  currentPath.value = targetPath
  
  if (targetPath === '/dashboard') {
    lastActivePath.value = '/dashboard'
  } else if (targetPath === '/dashboard/domains') {
    lastActivePath.value = '/dashboard/domains'
  }

  // 如果切换回到主面板且目前无数据，拉取域名数据
  if (targetPath !== '/login' && domains.value.length === 0) {
    loadDomains(false)
  }
}

// API 数据交互
const checkAuthStatus = async () => {
  try {
    const res = await fetch("/api/auth/status")
    const data = await res.json()
    
    isSystemInitialized.value = data.has_users
    loggedIn.value = data.logged_in
    
    navigate(window.location.pathname, false)
  } catch (e) {
    showToast("连接服务器认证失败", "error")
  }
}

const loadDomains = async (isManual = false) => {
  domainsLoading.value = true
  try {
    const url = isManual ? "/api/domains?refresh=true" : "/api/domains"
    const res = await apiFetch(url, {}, triggerOnUnauthorized)
    if (!res) return
    
    if (!res.ok) throw new Error("API 请求失败")
    domains.value = await res.json()
    
    if (isManual) {
      showToast("已重新扫描获取全量域名状态")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("获取域名列表失败", "error")
    }
  } finally {
    domainsLoading.value = false
  }
}

const handleConfirmDelete = (domain) => {
  deleteTarget.value = domain
}

const handleUpdateDomain = (freshItem) => {
  const index = domains.value.findIndex(item => item.domain === freshItem.domain)
  if (index !== -1) {
    domains.value[index] = freshItem
  }
}

const handleLogout = async () => {
  try {
    const res = await fetch("/api/auth/logout", { method: "POST" })
    if (res.ok) {
      showToast("已安全注销退出")
      loggedIn.value = false
      closeSettingsDrawer()
      navigate('/dashboard')
    }
  } catch (e) {
    showToast("退出登录请求失败", "error")
  }
}

const handleAuthSuccess = (success) => {
  if (success) {
    loggedIn.value = true
    navigate('/dashboard')
    loadDomains(false)
  } else {
    // 首次注册管理员账号完毕，去登录
    isSystemInitialized.value = true
    navigate('/login')
  }
}

const closeSettingsDrawer = () => {
  navigate(lastActivePath.value || '/dashboard')
}

const onSettingsSaved = (needRefreshList) => {
  if (needRefreshList) {
    loadDomains(false)
  }
}

onMounted(() => {
  initTheme()
  checkAuthStatus()

  window.addEventListener('popstate', () => {
    navigate(window.location.pathname, false)
  })
})
</script>
