<template>
  <div @click="handleBackgroundClick">
    <!-- 仪表盘统计区块 -->
    <div class="dashboard">
      <!-- 系统整体健康度 -->
      <div class="glass-card health-card">
        <span class="health-title">系统整体健康度</span>
        <span class="health-value" :style="{ color: healthColor }">{{ healthScore }}%</span>
        <div class="health-bar-container">
          <div class="health-bar" :style="{ width: `${healthScore}%`, background: healthGradient }"></div>
        </div>
        <span class="health-status-desc">{{ healthDesc }}</span>
      </div>

      <!-- 分类统计网格 -->
      <div class="glass-card stats-grid">
        <!-- 正常 -->
        <div class="stat-item ok" :class="{ active: currentFilter === '正常' }" @click="setFilter('正常')">
          <div class="stat-icon"><ShieldCheck style="width: 16px; height: 16px;" /></div>
          <span class="stat-label">正常</span>
          <span class="stat-count">{{ stats.ok }}</span>
        </div>
        <!-- 提醒 -->
        <div class="stat-item info" :class="{ active: currentFilter === '提醒' }" @click="setFilter('提醒')">
          <div class="stat-icon"><Info style="width: 16px; height: 16px;" /></div>
          <span class="stat-label">提醒</span>
          <span class="stat-count">{{ stats.info }}</span>
        </div>
        <!-- 警告 -->
        <div class="stat-item warn" :class="{ active: currentFilter === '警告' }" @click="setFilter('警告')">
          <div class="stat-icon"><AlertTriangle style="width: 16px; height: 16px;" /></div>
          <span class="stat-label">警告</span>
          <span class="stat-count">{{ stats.warn }}</span>
        </div>
        <!-- 严重 -->
        <div class="stat-item crit" :class="{ active: currentFilter === '严重' }" @click="setFilter('严重')">
          <div class="stat-icon"><AlertOctagon style="width: 16px; height: 16px;" /></div>
          <span class="stat-label">严重</span>
          <span class="stat-count">{{ stats.crit }}</span>
        </div>
        <!-- 失败 -->
        <div class="stat-item fail" :class="{ active: currentFilter === '失败' }" @click="setFilter('失败')">
          <div class="stat-icon"><XCircle style="width: 16px; height: 16px;" /></div>
          <span class="stat-label">失败</span>
          <span class="stat-count">{{ stats.fail }}</span>
        </div>
      </div>
    </div>

    <!-- 数据只读列表卡片 -->
    <div class="glass-card" style="padding: 0; overflow: hidden;">
      <!-- 监控大屏工具栏 -->
      <div class="toolbar" style="justify-content: flex-end;">
        <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
          <!-- 搜索输入 -->
          <div class="search-wrapper">
            <Search class="input-icon" style="width: 16px; height: 16px;" />
            <input 
              type="text" 
              v-model="searchQuery" 
              class="input-field" 
              placeholder="过滤域名/端口..." 
            >
            <X 
              v-if="searchQuery" 
              class="search-clear" 
              style="display: block; width: 14px; height: 14px;" 
              @click="searchQuery = ''" 
            />
          </div>
          <!-- 快速过滤器 Tab -->
          <div class="filter-tabs">
            <button class="tab-btn" :class="{ active: quickFilter === '全部' }" @click="setQuickFilter('全部')">全部</button>
            <button class="tab-btn" :class="{ active: quickFilter === '关注' }" @click="setQuickFilter('关注')">需关注</button>
          </div>
        </div>
      </div>
      
      <!-- 只读表格数据 -->
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
            </tr>
          </thead>
          <tbody>
            <!-- 骨架屏加载状态 -->
            <template v-if="loading && domains.length === 0">
              <tr class="skeleton-row" v-for="i in 3" :key="i">
                <td><div class="skeleton-bar skeleton-domain"></div></td>
                <td><div class="skeleton-bar skeleton-port"></div></td>
                <td><div class="skeleton-bar skeleton-badge"></div></td>
                <td><div class="skeleton-bar skeleton-days"></div></td>
                <td><div class="skeleton-bar skeleton-date"></div></td>
              </tr>
            </template>
            <!-- 暂无数据提示 -->
            <tr v-else-if="filteredDomains.length === 0">
              <td colspan="5" class="empty-state">
                <div class="empty-icon"><ShieldAlert style="width: 44px; height: 44px;" /></div>
                <div class="empty-title">暂无数据</div>
                <div class="empty-desc">没有找到符合当前过滤条件的监控条目。</div>
              </td>
            </tr>
            <!-- 真实数据渲染 -->
            <tr v-else v-for="item in filteredDomains" :key="item.domain">
              <td class="domain-cell">
                <div>{{ getParsedDomain(item.domain).host }}</div>
                <div v-if="item.ssl.ip" style="font-size: 11px; color: var(--text-muted); font-weight: normal; margin-top: 2px;">
                  {{ item.ssl.ip }}
                </div>
              </td>
              <td class="port-cell">{{ getParsedDomain(item.domain).port }}</td>
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
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { 
  ShieldCheck, Info, AlertTriangle, AlertOctagon, XCircle, Search, X, ShieldAlert,
  ChevronsUpDown, ChevronUp, ChevronDown 
} from 'lucide-vue-next'
import { parseDomain } from '../utils/domain'

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

const currentFilter = ref('全部')
const quickFilter = ref('全部')
const searchQuery = ref('')
const sortKey = ref('')
const sortOrder = ref('asc') // 'asc' or 'desc'

const getParsedDomain = (domain) => {
  return parseDomain(domain)
}

// 统计数据
const stats = computed(() => {
  let ok = 0, info = 0, warn = 0, crit = 0, fail = 0
  props.domains.forEach(item => {
    const ssl = item.ssl
    if (!ssl.success) {
      fail++
    } else {
      switch (ssl.level) {
        case '正常': ok++; break
        case '提醒': info++; break
        case '警告': warn++; break
        case '严重': crit++; break
      }
    }
  })
  return { ok, info, warn, crit, fail }
})

// 系统健康评分与描述
const healthScore = computed(() => {
  const total = props.domains.length
  if (total === 0) return 0
  const totalPoints = (stats.value.ok * 100) + (stats.value.info * 80) + (stats.value.warn * 50)
  return Math.round(totalPoints / total)
})

const healthColor = computed(() => {
  const score = healthScore.value
  if (score >= 90) return 'var(--status-ok)'
  if (score >= 70) return 'var(--status-info)'
  if (score >= 50) return 'var(--status-warn)'
  return 'var(--status-crit)'
})

const healthGradient = computed(() => {
  const score = healthScore.value
  if (score >= 90) return 'linear-gradient(90deg, #3b82f6 0%, #10b981 100%)'
  if (score >= 70) return 'linear-gradient(90deg, #3b82f6 0%, #fbbf24 100%)'
  if (score >= 50) return 'linear-gradient(90deg, #fbbf24 0%, #f97316 100%)'
  return 'linear-gradient(90deg, #ef4444 0%, #b91c1c 100%)'
})

const healthDesc = computed(() => {
  const total = props.domains.length
  if (total === 0) return "系统就绪，等待导入域名数据。"
  const score = healthScore.value
  if (score === 100) return `全部 ${total} 个域名的证书均安全运行中。`
  if (score >= 80) return `有证书临近过期，系统处于轻微提醒级别。`
  if (score >= 50) return `部分证书即将过期，请及时跟进续期。`
  return `严重危险！检测到即将过期或已损坏的证书！`
})

// 筛选与排序处理
const setFilter = (type) => {
  if (currentFilter.value === type) {
    currentFilter.value = '全部' // 允许双击取消
  } else {
    currentFilter.value = type
    quickFilter.value = '全部' // 清理快捷筛选
  }
}

const setQuickFilter = (type) => {
  quickFilter.value = type
  currentFilter.value = '全部' // 清除分类筛选
}

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

// 最终展示在列表的域名列表
const filteredDomains = computed(() => {
  let list = props.domains.filter(item => {
    // 搜索过滤
    const parsed = parseDomain(item.domain)
    const query = searchQuery.value.trim().toLowerCase()
    const matchesSearch = parsed.host.toLowerCase().includes(query) || parsed.port.includes(query)
    if (!matchesSearch) return false

    // 指标卡片过滤
    if (currentFilter.value !== '全部') {
      if (currentFilter.value === '失败') {
        return !item.ssl.success
      }
      return item.ssl.success && item.ssl.level === currentFilter.value
    }

    // 快捷 Tab 过滤 (全部 vs 需关注)
    if (quickFilter.value === '关注') {
      return !item.ssl.success || item.ssl.level !== '正常'
    }

    return true
  })

  // 排序
  if (sortKey.value) {
    list.sort((a, b) => {
      let valA, valB
      
      if (sortKey.value === 'domain') {
        valA = parseDomain(a.domain).host
        valB = parseDomain(b.domain).host
      } else if (sortKey.value === 'port') {
        valA = parseInt(parseDomain(a.domain).port) || 443
        valB = parseInt(parseDomain(b.domain).port) || 443
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

const handleBackgroundClick = (event) => {
  if (currentFilter.value === '全部' && quickFilter.value === '全部') return
  
  const isStatItem = event.target.closest('.stat-item')
  const isToolbar = event.target.closest('.toolbar')
  const isTable = event.target.closest('.table-container')
  
  if (!isStatItem && !isToolbar && !isTable) {
    currentFilter.value = '全部'
    quickFilter.value = '全部'
  }
}
</script>
