<template>
  <div class="modal-overlay" :class="{ show: show }">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-header-icon">
          <AlertTriangle style="width: 20px; height: 20px;" />
        </div>
        <div class="modal-title">删除确认</div>
      </div>
      <div class="modal-body">
        确定要停止对域名 <strong style="color:var(--danger-color);">{{ displayHost }}</strong> (端口: {{ displayPort }}) 的 SSL 监控吗？删除后配置不可恢复。
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="loading" @click="confirmDelete" style="background: var(--danger-color);">
          {{ loading ? '删除中...' : '确定删除' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, inject } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import { parseDomain } from '../utils/domain'
import { apiFetch } from '../utils/api'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  domain: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'confirmed'])

const showToast = inject('showToast')
const triggerOnUnauthorized = inject('triggerOnUnauthorized')

const loading = ref(false)

const parsed = computed(() => {
  if (!props.domain) return { host: '', port: '' }
  return parseDomain(props.domain)
})

const displayHost = computed(() => parsed.value.host)
const displayPort = computed(() => parsed.value.port)

const close = () => {
  emit('close')
}

const confirmDelete = async () => {
  if (!props.domain) return
  loading.value = true
  try {
    const res = await apiFetch("/api/domains", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain: props.domain })
    }, triggerOnUnauthorized)
    if (!res) return

    const data = await res.json()
    if (res.ok) {
      showToast("已删除监控目标")
      emit('confirmed')
      close()
    } else {
      showToast(data.error || "删除失败", "error")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("删除异常", "error")
    }
  } finally {
    loading.value = false
  }
}
</script>
