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
              placeholder="输入域名，如 example.com"
              aria-label="添加监控域名"
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
              placeholder="搜索域名或备注..."
              aria-label="搜索管理列表中的域名、IP 或备注"
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
      <TableScroll ref="tableScroll">
        <table class="monitor-table manage-table">
          <thead>
            <tr>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'domain' }" @click="handleSort('domain')">
                <div class="sort-header-container">
                  <span>监控域名</span>
                  <component :is="getSortIcon('domain')" class="sort-icon" />
                </div>
              </th>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'ip' }" @click="handleSort('ip')">
                <div class="sort-header-container">
                  <span>解析 IP</span>
                  <component :is="getSortIcon('ip')" class="sort-icon" />
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
                  <span>证书到期时间</span>
                  <component :is="getSortIcon('expire')" class="sort-icon" />
                </div>
              </th>
              <th>检测异常</th>
              <th class="sortable" :class="{ 'active-sort': sortKey === 'remark' }" @click="handleSort('remark')">
                <div class="sort-header-container">
                  <span>备注</span>
                  <component :is="getSortIcon('remark')" class="sort-icon" />
                </div>
              </th>
              <th class="actions-heading">操作</th>
            </tr>
          </thead>
          <tbody>
            <!-- 骨架屏加载 -->
            <template v-if="loading && domains.length === 0">
              <tr class="skeleton-row" v-for="i in 3" :key="i">
                <td><div class="skeleton-bar skeleton-domain"></div></td>
                <td><div class="skeleton-bar skeleton-port"></div></td>
                <td><div class="skeleton-bar skeleton-port"></div></td>
                <td><div class="skeleton-bar skeleton-domain"></div></td>
                <td><div class="skeleton-bar skeleton-badge"></div></td>
                <td><div class="skeleton-bar skeleton-days"></div></td>
                <td><div class="skeleton-bar skeleton-date"></div></td>
                <td><div class="skeleton-bar skeleton-date"></div></td>
                <td><div class="skeleton-bar skeleton-date"></div></td>
                <td><div class="skeleton-bar skeleton-port" style="margin: 0 auto;"></div></td>
              </tr>
            </template>
            <!-- 无数据提示 -->
            <tr v-else-if="filteredManageDomains.length === 0">
              <td colspan="10" class="empty-state">
                <div class="empty-icon"><ShieldAlert style="width: 44px; height: 44px;" /></div>
                <div class="empty-title">暂无数据</div>
                <div class="empty-desc">管理列表中无监控条目。</div>
              </td>
            </tr>
            <!-- 真实渲染列表 -->
            <tr 
              v-else 
              v-for="item in pagedManageDomains"
              :key="item.domain" 
              :class="{ 'refreshing-row': singleLoadingMap[item.domain] }"
            >
              <td class="domain-cell" :title="item.ssl.punycode_host && item.ssl.punycode_host !== (item.ssl.display_host || getParsedDomain(item.domain).host) ? `${item.ssl.display_host || getParsedDomain(item.domain).host} (${item.ssl.punycode_host})` : item.domain">
                {{ item.ssl.display_host || getParsedDomain(item.domain).host }}
              </td>
              <td class="ip-cell" :title="item.ssl.ip || ''" style="font-size: 13px; font-family: monospace; color: var(--text-secondary);">
                {{ item.ssl.ip || '-' }}
              </td>
              <td class="port-cell">{{ getParsedDomain(item.domain).port }}</td>
              <td class="issuer-cell" :title="item.ssl.issuer || ''" style="font-size: 13px; color: var(--text-secondary);">
                {{ item.ssl.issuer || '-' }}
              </td>
              <td>
                <span class="badge" :class="getBadgeClass(item.ssl)">
                  <span>{{ item.ssl.level }}</span>
                </span>
              </td>
              <td class="days-value" :class="getDaysClass(item.ssl)">
                {{ item.ssl.success ? `${item.ssl.days} 天` : '-' }}
              </td>
              <td class="date-cell" :title="item.ssl.success ? item.ssl.expire : ''">{{ item.ssl.success ? item.ssl.expire : '-' }}</td>
              <td class="date-cell"><TableDetail v-if="item.enabled !== false && item.ssl.error" :text="item.ssl.error" label="检测异常" /></td>
              <td class="remark-cell"><TableDetail v-if="item.remark" :text="item.remark" label="备注" /></td>
              <td style="text-align: center;">
                <div class="action-cell" @pointerover="showActionTooltip" @pointerout="hideActionTooltipOnExit" @focusin="showActionTooltip" @focusout="hideActionTooltipOnExit" @click="hideActionTooltip">
                  <button
                    type="button"
                    class="monitor-switch"
                    :class="{ 'is-on': item.enabled !== false }"
                    role="switch"
                    :aria-checked="item.enabled !== false"
                    :disabled="switchLoadingMap[item.domain] || singleLoadingMap[item.domain]"
                    :data-tooltip="item.enabled === false ? '启用监控' : '停用监控'"
                    :aria-label="item.enabled === false ? '启用监控' : '停用监控'"
                    @click="toggleEnabled(item)"
                  >
                    <Loader v-if="switchLoadingMap[item.domain]" class="switch-spinner spin" aria-hidden="true" />
                    <span v-else class="switch-thumb" aria-hidden="true"></span>
                  </button>
                  <button 
                    class="btn-icon-only domain-action-button"
                    :disabled="singleLoadingMap[item.domain]"
                    @click="openEdit(item)"
                    data-tooltip="编辑域名和备注"
                    aria-label="编辑域名和备注"
                  >
                    <Edit2 class="action-icon" />
                  </button>
                  <button
                    class="btn-icon-only domain-action-button"
                    @click="refreshSingle(item.domain)" 
                    :disabled="singleLoadingMap[item.domain] || item.enabled === false"
                    data-tooltip="刷新该域名"
                    aria-label="刷新该域名"
                  >
                    <RefreshCw :class="['action-icon', { spin: singleLoadingMap[item.domain] }]" />
                  </button>
                  <button 
                    class="btn-icon-only domain-action-button action-delete"
                    :disabled="singleLoadingMap[item.domain]"
                    @click="$emit('confirm-delete', item.domain)" 
                    data-tooltip="删除域名"
                    aria-label="删除域名"
                  >
                    <Trash2 class="action-icon" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </TableScroll>
      <TablePagination
        :total="filteredManageDomains.length"
        :page="currentPage"
        :page-size="pageSize"
        page-size-id="manage-page-size"
        @update:page="changePage"
        @update:pageSize="changePageSize"
      />
    </div>

    <!-- 编辑域名弹窗 -->
    <EditModal 
      :show="showEditModal" 
      :target-domain="editTargetDomain" 
      :target-remark="editTargetRemark"
      @close="showEditModal = false" 
      @updated="handleEditUpdated" 
    />
    <Teleport to="body">
      <div
        v-if="actionTooltip.visible"
        class="action-tooltip"
        :class="{ below: actionTooltip.below }"
        :style="{ left: `${actionTooltip.left}px`, top: `${actionTooltip.top}px`, transform: actionTooltip.below ? 'translateX(-50%)' : 'translate(-50%, -100%)' }"
        role="tooltip"
      >{{ actionTooltip.text }}</div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, inject, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import { 
  PlusCircle, Plus, ListPlus, Search, X, ShieldAlert, RefreshCw, Trash2, Loader, Edit2,
  ChevronsUpDown, ChevronUp, ChevronDown
} from 'lucide-vue-next'
import { parseDomain, domainRegex } from '../utils/domain'
import { apiFetch } from '../utils/api'
import EditModal from './EditModal.vue'
import TableScroll from './TableScroll.vue'
import TablePagination from './TablePagination.vue'
import TableDetail from './TableDetail.vue'

const showEditModal = ref(false)
const editTargetDomain = ref('')
const editTargetRemark = ref('')
const actionTooltip = reactive({ visible: false, text: '', left: 0, top: 0, below: false })

const showActionTooltip = (event) => {
  const button = event.target.closest?.('[data-tooltip]')
  if (!button || !event.currentTarget.contains(button) || button.disabled) return
  const bounds = button.getBoundingClientRect()
  actionTooltip.text = button.dataset.tooltip
  actionTooltip.left = Math.max(60, Math.min(window.innerWidth - 60, bounds.left + bounds.width / 2))
  actionTooltip.below = bounds.top < 42
  actionTooltip.top = actionTooltip.below ? bounds.bottom + 8 : bounds.top - 8
  actionTooltip.visible = true
}

const hideActionTooltip = () => { actionTooltip.visible = false }
const hideActionTooltipOnExit = (event) => {
  const button = event.target.closest?.('[data-tooltip]')
  if (!button || !button.contains(event.relatedTarget)) hideActionTooltip()
}

onMounted(() => {
  window.addEventListener('scroll', hideActionTooltip, true)
  window.addEventListener('resize', hideActionTooltip)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', hideActionTooltip, true)
  window.removeEventListener('resize', hideActionTooltip)
})

const openEdit = (item) => {
  editTargetDomain.value = item.domain
  editTargetRemark.value = item.remark || ''
  showEditModal.value = true
}

const handleEditUpdated = () => {
  emit('refresh')
}

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
const switchLoadingMap = reactive({})

const refreshSingle = async (domainStr) => {
  singleLoadingMap[domainStr] = true
  try {
    const res = await apiFetch(`/api/domains/check?domain=${encodeURIComponent(domainStr)}`, {}, triggerOnUnauthorized)
    if (!res) return
    
    if (!res.ok) {
      const error = await res.json().catch(() => ({}))
      throw new Error(error.error || "检查失败")
    }
    const freshItem = await res.json()
    
    // 更新本地列表对应域名状态
    const index = props.domains.findIndex(item => item.domain === domainStr)
    if (index !== -1) {
      emit('update-domain', freshItem)
    }
    
    showToast(
      freshItem.ssl.success
        ? `域名 ${parseDomain(domainStr).host} 已独立刷新完成`
        : `域名 ${parseDomain(domainStr).host} 检测失败：${freshItem.ssl.error || '未知错误'}`,
      freshItem.ssl.success ? 'success' : 'error'
    )
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast(`刷新域名失败：${e.message}`, "error")
    }
  } finally {
    singleLoadingMap[domainStr] = false
  }
}

const toggleEnabled = async (item) => {
  switchLoadingMap[item.domain] = true
  try {
    const enabled = item.enabled === false
    const res = await apiFetch('/api/domains/enabled', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain: item.domain, enabled })
    }, triggerOnUnauthorized)
    if (!res) return
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || '更新失败')
    showToast(enabled ? '已启用域名监控' : '已停用域名监控')
    emit('refresh')
  } catch (e) {
    showToast(`更新监控状态失败：${e.message}`, 'error')
  } finally {
    switchLoadingMap[item.domain] = false
  }
}

// 搜索与排序
const searchManageQuery = ref('')
const sortKey = ref('expire')
const sortOrder = ref('asc')
const currentPage = ref(1)
const pageSize = ref(50)
const tableScroll = ref(null)

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
  if (ssl.level === '已停用') return 'badge-disabled'
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
    const displayHost = (item.ssl.display_host || parsed.host).toLowerCase()
    const punyHost = (item.ssl.punycode_host || parsed.host).toLowerCase()
    const issuerStr = (item.ssl.issuer || '').toLowerCase()
    const ipStr = (item.ssl.ip || '').toLowerCase()
    const remarkStr = (item.remark || '').toLowerCase()

    return displayHost.includes(query) || punyHost.includes(query) || 
           parsed.port.includes(query) || issuerStr.includes(query) || ipStr.includes(query) || remarkStr.includes(query)
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
      } else if (sortKey.value === 'ip') {
        valA = a.ssl.ip || ''
        valB = b.ssl.ip || ''
      } else if (sortKey.value === 'issuer') {
        valA = a.ssl.issuer || ''
        valB = b.ssl.issuer || ''
      } else if (sortKey.value === 'remark') {
        valA = a.remark || ''
        valB = b.remark || ''
      } else if (sortKey.value === 'status') {
        const priority = { '正常': 4, '提醒': 3, '警告': 2, '严重': 1, '失败': 0 }
        valA = a.ssl.success ? priority[a.ssl.level] : 0
        valB = b.ssl.success ? priority[b.ssl.level] : 0
      } else if (sortKey.value === 'days') {
        valA = a.ssl.success ? a.ssl.days : 99999
        valB = b.ssl.success ? b.ssl.days : 99999
      } else if (sortKey.value === 'expire') {
        valA = a.ssl.success && a.ssl.expire ? a.ssl.expire : '9999'
        valB = b.ssl.success && b.ssl.expire ? b.ssl.expire : '9999'
      }

      if (valA < valB) return sortOrder.value === 'asc' ? -1 : 1
      if (valA > valB) return sortOrder.value === 'asc' ? 1 : -1
      return 0
    })
  }

  return list
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredManageDomains.value.length / pageSize.value)))
const pagedManageDomains = computed(() => filteredManageDomains.value.slice((currentPage.value - 1) * pageSize.value, currentPage.value * pageSize.value))

watch([searchManageQuery, sortKey, sortOrder], () => { currentPage.value = 1 })
watch(totalPages, count => { if (currentPage.value > count) currentPage.value = count })

const changePage = async page => {
  if (page < 1 || page > totalPages.value || page === currentPage.value) return
  currentPage.value = page
  await nextTick()
  tableScroll.value?.scrollToStart()
}

const changePageSize = async size => {
  pageSize.value = size
  currentPage.value = 1
  await nextTick()
  tableScroll.value?.scrollToStart()
}
</script>

<style scoped>
.action-tooltip {
  position: fixed;
  z-index: 9000;
  padding: 6px 9px;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.94);
  color: #f8fafc;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.18);
}
</style>
