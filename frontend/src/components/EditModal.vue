<template>
  <div class="modal-overlay" :class="{ show: show }" @click="close">
    <div class="modal" @click.stop style="max-width:480px;">
      <div class="modal-header">
        <div class="modal-header-icon" style="background:var(--primary-glow); color:var(--primary-color);">
          <Edit2 style="width: 20px; height: 20px;" />
        </div>
        <div class="modal-title">修改监控域名</div>
      </div>
      <div class="modal-body" style="margin-bottom:20px;">
        <div style="font-size:12px; color:var(--text-secondary); margin-bottom:12px;">
          修改当前选中的域名及服务端口配置（支持更改端口，如 <code>example.com:8443</code>）：
        </div>
        
        <div class="input-wrapper" style="margin-bottom: 8px;">
          <Globe class="input-icon" style="width: 16px; height: 16px;" />
          <input 
            type="text" 
            v-model="editDomainInput" 
            :class="['input-field', { invalid: !isValid }]" 
            placeholder="如 example.com 或 example.com:8443" 
            @keyup.enter="handleSave"
            @input="validate"
          >
          <div class="validation-hint" :style="{ display: !isValid ? 'block' : 'none' }">域名格式不正确</div>
        </div>
        <div style="font-size: 11px; color: var(--text-muted);">
          原配置: <code style="font-weight: bold; color: var(--text-color);">{{ targetDomain }}</code>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" :disabled="loading" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="loading || !editDomainInput.trim()" @click="handleSave">
          <Loader v-if="loading" class="spin" style="width: 14px; height: 14px;" />
          <span>{{ loading ? '保存中...' : '保存修改' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, inject } from 'vue'
import { Edit2, Globe, Loader } from 'lucide-vue-next'
import { parseDomain, domainRegex } from '../utils/domain'
import { apiFetch } from '../utils/api'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  targetDomain: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'updated'])

const showToast = inject('showToast', (msg) => alert(msg))
const triggerOnUnauthorized = inject('triggerOnUnauthorized')

const editDomainInput = ref('')
const isValid = ref(true)
const loading = ref(false)

watch(() => props.show, (newVal) => {
  if (newVal) {
    editDomainInput.value = props.targetDomain || ''
    isValid.value = true
  }
})

const validate = () => {
  const val = editDomainInput.value.trim()
  if (!val) {
    isValid.value = true
    return
  }
  const parsed = parseDomain(val)
  const isDomainOrIpv4 = domainRegex.test(parsed.host)
  const colonCount = (parsed.host.match(/:/g) || []).length
  const isIpv6 = /^[0-9a-fA-F:]+$/.test(parsed.host) && colonCount >= 2 && colonCount <= 7

  isValid.value = (isDomainOrIpv4 || isIpv6)
}

const close = () => {
  if (!loading.value) {
    emit('close')
  }
}

const handleSave = async () => {
  validate()
  if (!isValid.value) {
    showToast("请输入有效的域名格式", "error")
    return
  }

  const newDomainStr = editDomainInput.value.trim()
  if (!newDomainStr) return

  if (newDomainStr === props.targetDomain) {
    close()
    return
  }

  loading.value = true
  try {
    const res = await apiFetch("/api/domains", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        old_domain: props.targetDomain,
        new_domain: newDomainStr
      })
    }, triggerOnUnauthorized)
    
    if (!res) return

    const data = await res.json()
    if (res.ok) {
      showToast(`域名成功修改为 ${data.domain}`, 'success')
      emit('updated', data)
      close()
    } else {
      showToast(data.error || "修改失败", "error")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("修改发生异常", "error")
    }
  } finally {
    loading.value = false
  }
}
</script>
