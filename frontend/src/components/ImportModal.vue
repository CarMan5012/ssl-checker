<template>
  <div class="modal-overlay" :class="{ show: show }" @click="close">
    <div class="modal" @click.stop style="max-width:550px;">
      <div class="modal-header">
        <div class="modal-header-icon" style="background:var(--primary-glow); color:var(--primary-color);">
          <ListPlus style="width: 20px; height: 20px;" />
        </div>
        <div class="modal-title">批量导入域名监控</div>
      </div>
      <div class="modal-body" style="margin-bottom:16px;">
        <p style="font-size:12px; color:var(--text-secondary); margin-bottom:10px;">
          每行填写一个域名或带端口，支持粘贴带协议的前缀和行尾备注：
        </p>
        <textarea 
          v-model="importText" 
          class="input-field" 
          style="height:200px; padding:12px; font-family:monospace; resize:none;" 
          placeholder="example.com&#10;https://github.com # 备注&#10;my-server.local:8443"
        ></textarea>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="close">取消</button>
        <button class="btn btn-primary" :disabled="loading" @click="executeImport">
          {{ loading ? '导入中...' : '确定导入' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, inject } from 'vue'
import { ListPlus } from 'lucide-vue-next'
import { apiFetch } from '../utils/api'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'imported'])

const showToast = inject('showToast')
const triggerOnUnauthorized = inject('triggerOnUnauthorized')

const importText = ref('')
const loading = ref(false)

watch(() => props.show, (newVal) => {
  if (newVal) {
    importText.value = ''
  }
})

const close = () => {
  emit('close')
}

const executeImport = async () => {
  const text = importText.value.trim()
  if (!text) {
    showToast("请输入导入内容", "error")
    return
  }

  loading.value = true
  try {
    const res = await apiFetch("/api/domains/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains: text })
    }, triggerOnUnauthorized)
    if (!res) return

    const data = await res.json()
    if (res.ok) {
      showToast(`成功导入 ${data.added_count} 个域名，过滤 ${data.duplicate_count} 个重复值`)
      emit('imported')
      close()
    } else {
      showToast(data.error || "导入失败", "error")
    }
  } catch (e) {
    if (e.message !== "Unauthorized") {
      showToast("导入发生异常", "error")
    }
  } finally {
    loading.value = false
  }
}
</script>
