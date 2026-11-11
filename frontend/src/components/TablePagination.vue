<template>
  <div class="table-pagination">
    <div class="pagination-summary">共 {{ total }} 条<span v-if="total">，显示 {{ start }}–{{ end }} 条</span></div>
    <div class="pagination-controls">
      <label class="page-size-label" :for="pageSizeId">每页</label>
      <select :id="pageSizeId" class="page-size-select" :value="pageSize" @change="$emit('update:pageSize', Number($event.target.value))">
        <option :value="20">20 条</option>
        <option :value="50">50 条</option>
        <option :value="100">100 条</option>
      </select>
      <button type="button" class="page-button" :disabled="page <= 1" @click="$emit('update:page', page - 1)">上一页</button>
      <span class="page-position">{{ page }} / {{ totalPages }}</span>
      <button type="button" class="page-button" :disabled="page >= totalPages" @click="$emit('update:page', page + 1)">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  total: { type: Number, required: true },
  page: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  pageSizeId: { type: String, required: true }
})

defineEmits(['update:page', 'update:pageSize'])

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const start = computed(() => (props.page - 1) * props.pageSize + 1)
const end = computed(() => Math.min(props.page * props.pageSize, props.total))
</script>

<style scoped>
.table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-top: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
}

.pagination-controls { display: flex; align-items: center; gap: 8px; }
.pagination-summary, .page-position, .page-size-label { white-space: nowrap; }
.page-position { min-width: 48px; text-align: center; font-variant-numeric: tabular-nums; }
.page-size-select, .page-button {
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--input-bg);
  color: var(--text-secondary);
  font: inherit;
}
.page-size-select { cursor: pointer; }
.page-button { cursor: pointer; white-space: nowrap; }
.page-button:hover:not(:disabled) { color: var(--primary-color); border-color: var(--primary-color); }
.page-button:disabled { opacity: 0.45; cursor: not-allowed; }
.page-button:focus-visible, .page-size-select:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

@media (max-width: 640px) {
  .table-pagination { flex-wrap: wrap; }
  .pagination-controls { width: 100%; justify-content: space-between; }
}
</style>
