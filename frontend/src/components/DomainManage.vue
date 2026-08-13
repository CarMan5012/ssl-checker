<template>
  <div>
    <div class="glass-card" style="padding: 0; overflow: hidden;">
      <!-- 管理工具栏 -->
      <div class="toolbar">
        <div class="input-group">
          <div class="input-wrapper">
            <PlusCircle class="input-icon" style="width: 16px; height: 16px;" />
            <input 
              type="text" 
              v-model="newDomain" 
              :class="['input-field', { invalid: !isInputValid }]" 
              placeholder="输入单个域名，如 google.com" 
              @keyup.enter="handleAdd"
              @input="validateInput"
            >
            <div class="validation-hint" :style="{ display: !isInputValid ? 'block' : 'none' }">域名格式不正确</div>
          </div>
          <button class="btn btn-primary" :disabled="addLoading" @click="handleAdd">
            <Loader v-if="addLoading" class="spin" style="width: 15px; height: 15px;" />
            <Plus v-else style="width: 15px; height: 15px;" />
            <span>添加域名</span>
          </button>
          <button class="btn btn-secondary" @click="$emit('open-import')">
            <ListPlus style="width: 15px; height: 15px;" />
            <span>批量导入</span>
          </button>
        </div>
        
        <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
          <div class="search-wrapper">
            <Search class="input-icon" style="width: 16px; height: 16px;" />
            <input 
              type="text" 
              v-model="searchManageQuery" 
              class="input-field" 
              placeholder="过滤管理列表..." 
            >
            <X 
              v-if="searchManageQuery" 
              class="search-clear" 
              style="display: block; width: 14px; height: 14px;" 
              @click="searchManageQuery = ''" 
            />
          </div>
        </div>
      </div>

      <!-- 可管理表格数据 -->
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'domain' }" @click="handleSort('domain')">
                <div class="sort-header-container">
                  <span>监控域名</span>
                  <component :is="getSortIcon('domain')" class="sort-icon" />
                </div>
              </th>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'port' }" @click="handleSort('port')">
                <div class="sort-header-container">
                  <span>端口</span>
                  <component :is="getSortIcon('port')" class="sort-icon" />
                </div>
              </th>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'issuer' }" @click="handleSort('issuer')">
                <div class="sort-header-container">
                  <span>颁发者 (组织O)</span>
                  <component :is="getSortIcon('issuer')" class="sort-icon" />
                </div>
              </th>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'status' }" @click="handleSort('status')">
                <div class="sort-header-container">
                  <span>状态</span>
                  <component :is="getSortIcon('status')" class="sort-icon" />
                </div>
              </th>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'days' }" @click="handleSort('days')">
                <div class="sort-header-container">
                  <span>到期余天</span>
                  <component :is="getSortIcon('days')" class="sort-icon" />
                </div>
              </th>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'expire' }" @click="handleSort('expire')">
                <div class="sort-header-container">
                  <span>过期时间 / 错误原因</span>
                  <component :is="getSortIcon('expire')" class="sort-icon" />
                </div>
              </th>
              <th style="width: 100px; text-align: center;">操作</th>
            </tr>
          </thead>
          <tbody>
            <!-- 骨架屏加载 -->
            <template v-if="loading && domains.length === 0">
              <tr class="skeleton-row" v-for="i in 3" :key="i">
                <td><div class="skeleton-bar skeleton-domain"></div></td>
                <td><div class="skeleton-bar skeleton-port"></div></td>
                <td><div class="skeleton-bar skeleton-domain"></div></td>
                <td><div class="skeleton-bar skeleton-badge"></div></td>
                <td><div class="skeleton-bar skeleton-days"></div></td>
                <td><div class="skeleton-bar skeleton-date"></div></td>
                <td><div class="skeleton-bar skeleton-port" style="margin: 0 auto;"></div></td>
              </tr>
            </template>
            <!-- 无数据提示 -->
            <tr v-else-if="filteredManageDomains.length === 0">
              <td colspan="7" class="empty-state">
                <div class="empty-icon"><ShieldAlert style="width: 44px; height: 44px;" /></div>
                <div class="empty-title">暂无数据</div>
                <div class="empty-desc">管理列表中无监控条目。</div>
              </td>
            </tr>
            <!-- 真实渲染列表 -->
            <tr 
              v-else 
              v-for="item in filteredManageDomains" 
              :key="item.domain" 
              :class="{ 'refreshing-row': singleLoadingMap[item.domain] }"
            >
              <td class="domain-cell">
                <div>{{ getParsedDomain(item.domain).host }}</div>
                <div v-if="item.ssl.ip" style="font-size: 11px; color: var(--text-muted); font-weight: normal; margin-top: 2px;">
                  {{ item.ssl.ip }}
                </div>
              </td>
              <td class="port-cell">{{ getParsedDomain(item.domain).port }}</td>
              <td class="issuer-cell" style="font-size: 13px; color: var(--text-secondary);">
                {{ item.ssl.issuer || '-' }}
              </td>
              <td>
                <span class="badge" :class="getBadgeClass(item.ssl)">
                  <span class="badge-dot"></span>
                  <span>{{ item.ssl.level }}</span>
                </span>
              </td>
              <td class="days-value" :class="getDaysClass(item.ssl)">
                {{ item.ssl.success ? `${item.ssl.days} 天` : '-' }}
              </td>
              <td class="date-cell">{{ item.ssl.success ? item.ssl.expire : item.ssl.error }}</td>
              <td style="text-align: center;">
                <div class="action-cell">
                  <button 
                    class="btn-secondary btn-icon-only" 
                    style="width:28px; height:28px; border-radius:6px;" 
                    :disabled="singleLoadingMap[item.domain]"
                    @click="refreshSingle(item.domain)" 
                    title="刷新该域名"
                  >
                    <RefreshCw :class="{ spin: singleLoadingMap[item.domain] }" style="width: 12px; height: 12px;" />
                  </button>
                  <button 
                    class="btn-danger-link" 
                    :disabled="singleLoadingMap[item.domain]"
                    @click="$emit('confirm-delete', item.domain)" 
                    title="删除"
                  >
                    <Trash2 style="width: 13px; height: 13px;" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, inject } from 'vue'
import { 
  PlusCircle, Plus, ListPlus, Search, X, ShieldAlert, RefreshCw, Trash2, Loader,
  ChevronsUpDown, ChevronUp, ChevronDown 
} from 'lucide-vue-next'
import { parseDomain, domainRegex } from '../utils/domain'
import { apiFetch } from '../utils/api'

const props = defineProps({
  domains: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['open-import', 'confirm-delete', 'refresh', 'update-domain'])

// 添加新域名逻辑
const newDomain = ref('')
const isInputValid = ref(true)
const addLoading = ref(false)

const showToast = inject('showToast', (msg) => alert(msg))
const triggerOnUnauthorized = inject('triggerOnUnauthorized')

const validateInput = () => {
  const val = newDomain.value.trim()
  if (!val) {
    isInputValid.value = true
    return
  }
  const parsed = parseDomain(val)
  const isDomainOrIpv4 = domainRegex.test(parsed.host)
  const colonCount = (parsed.host.match(/:/g) || []).length
  const isIpv6 = /^[0-9a-fA-F:]+$/.test(parsed.host) && colonCount >= 2 && colonCount <= 7

  isInputValid.value = (isDomainOrIpv4 || isIpv6)
}

const handleAdd = async () => {
  validateInput()
  if (!isInputValid.value) {
    showToast("请输入有效域名！", "error")
    return
  }

  const rawVal = newDomain.value.trim()
  if (!rawVal) return

  const parsed = parseDomain(rawVal)
  let formattedDomain = parsed.host
  if (parsed.port !== "443") {
    formattedDomain = `${parsed.host}:${parsed.port}`
  }

  addLoading.value = true
  try {
    const res = await apiFetch("/api/domains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain: formattedDomain })
    }, triggerOnUnauthorized)
    if (!res) return
    
    const data = await res.json()
    if (res.ok) {
      showToast(`域名 ${parsed.host} 成功添加监控`)
      newDomain.value = ""
      emit('refresh')
    } else {
      showToast(data.error || "添加失败", "error")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("添加失败，请重试", "error")
    }
  } finally {
    addLoading.value = false
  }
}

// 域名管理列表内单个重新检测逻辑
const singleLoadingMap = reactive({})

const refreshSingle = async (domainStr) => {
  singleLoadingMap[domainStr] = true
  try {
    const res = await apiFetch(`/api/domains/check?domain=${encodeURIComponent(domainStr)}`, {}, triggerOnUnauthorized)
    if (!res) return
    
    if (!res.ok) throw new Error("检查失败")
    const freshItem = await res.json()
    
    // 更新本地列表对应域名状态
    const index = props.domains.findIndex(item => item.domain === domainStr)
    if (index !== -1) {
      emit('update-domain', freshItem)
    }
    
    showToast(`域名 ${parseDomain(domainStr).host} 已独立刷新完成`)
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast(`刷新域名失败`, "error")
    }
  } finally {
    singleLoadingMap[domainStr] = false
  }
}

// 搜索与排序
const searchManageQuery = ref('')
const sortKey = ref('')
const sortOrder = ref('asc')

const getParsedDomain = (domain) => {
  return parseDomain(domain)
}

// 筛选排序
const handleSort = (key) => {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'asc'
  }
}

const getSortIcon = (key) => {
  if (sortKey.value !== key) return ChevronsUpDown
  return sortOrder.value === 'asc' ? ChevronUp : ChevronDown
}

const getBadgeClass = (ssl) => {
  if (!ssl.success) return 'badge-fail'
  switch (ssl.level) {
    case '正常': return 'badge-ok'
    case '提醒': return 'badge-info'
    case '警告': return 'badge-warn'
    case '严重': return 'badge-crit'
    default: return 'badge-fail'
  }
}

const getDaysClass = (ssl) => {
  if (!ssl.success) return ''
  switch (ssl.level) {
    case '正常': return 'days-ok'
    case '提醒': return 'days-info'
    case '警告': return 'days-warn'
    case '严重': return 'days-crit'
    default: return ''
  }
}

const filteredManageDomains = computed(() => {
  let list = props.domains.filter(item => {
    const parsed = parseDomain(item.domain)
    const query = searchManageQuery.value.trim().toLowerCase()
    const issuerStr = (item.ssl.issuer || '').toLowerCase()
    return parsed.host.toLowerCase().includes(query) || parsed.port.includes(query) || issuerStr.includes(query)
  })

  if (sortKey.value) {
    list.sort((a, b) => {
      let valA, valB
      
      if (sortKey.value === 'domain') {
        valA = parseDomain(a.domain).host
        valB = parseDomain(b.domain).host
      } else if (sortKey.value === 'port') {
        valA = parseInt(parseDomain(a.domain).port) || 443
        valB = parseInt(parseDomain(b.domain).port) || 443
      } else if (sortKey.value === 'issuer') {
        valA = a.ssl.issuer || ''
        valB = b.ssl.issuer || ''
      } else if (sortKey.value === 'status') {
        const priority = { '正常': 4, '提醒': 3, '警告': 2, '严重': 1, '失败': 0 }
        valA = a.ssl.success ? priority[a.ssl.level] : 0
        valB = b.ssl.success ? priority[b.ssl.level] : 0
      } else if (sortKey.value === 'days') {
        valA = a.ssl.success ? a.ssl.days : 99999
        valB = b.ssl.success ? b.ssl.days : 99999
      } else if (sortKey.value === 'expire') {
        valA = a.ssl.success ? a.ssl.expire : a.ssl.error
        valB = b.ssl.success ? b.ssl.expire : b.ssl.error
      }

      if (valA < valB) return sortOrder.value === 'asc' ? -1 : 1
      if (valA > valB) return sortOrder.value === 'asc' ? 1 : -1
      return 0
    })
  }

  return list
})
</script>
