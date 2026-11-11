<template>
  <button
    v-if="text"
    ref="trigger"
    type="button"
    class="table-detail-trigger"
    :aria-label="`${label}：${text}`"
    @mouseenter="open"
    @mouseleave="close"
    @focus="open"
    @blur="hide"
    @click="toggle"
  >{{ text }}</button>
  <Teleport to="body">
    <div
      v-if="visible"
      class="table-detail-popover"
      :style="{ left: `${left}px`, top: `${top}px`, transform: below ? 'none' : 'translateY(-100%)' }"
      role="tooltip"
    >{{ text }}</div>
  </Teleport>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'

defineProps({
  text: { type: String, default: '' },
  label: { type: String, required: true }
})

const trigger = ref(null)
const visible = ref(false)
const pinned = ref(false)
const left = ref(0)
const top = ref(0)
const below = ref(false)

const hide = () => {
  visible.value = false
  pinned.value = false
  window.removeEventListener('scroll', hide, true)
  window.removeEventListener('resize', hide)
  document.removeEventListener('pointerdown', hideOnOutsideClick, true)
}
const close = () => { if (!pinned.value) hide() }
const hideOnOutsideClick = (event) => {
  if (!trigger.value?.contains(event.target)) hide()
}
const open = () => {
  if (!trigger.value) return
  const bounds = trigger.value.getBoundingClientRect()
  left.value = Math.min(Math.max(bounds.left, 12), Math.max(12, window.innerWidth - 372))
  below.value = bounds.top < 120
  top.value = below.value ? bounds.bottom + 8 : bounds.top - 8
  if (!visible.value) {
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
  }
  visible.value = true
}
const toggle = () => {
  if (pinned.value) {
    hide()
  } else {
    open()
    pinned.value = true
    document.addEventListener('pointerdown', hideOnOutsideClick, true)
  }
}

onBeforeUnmount(hide)
</script>

<style scoped>
.table-detail-trigger {
  display: block;
  width: max-content;
  max-width: min(180px, 100%);
  margin: 0 auto;
  padding: 0;
  overflow: hidden;
  border: 0;
  background: none;
  color: var(--text-secondary);
  font: inherit;
  text-align: left;
  text-decoration: underline dotted var(--text-muted);
  text-underline-offset: 3px;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: help;
}
.table-detail-trigger:hover, .table-detail-trigger:focus-visible { color: var(--primary-color); }
.table-detail-trigger:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.table-detail-popover {
  position: fixed;
  z-index: 9000;
  max-width: min(360px, calc(100vw - 24px));
  padding: 9px 12px;
  border-radius: 8px;
  background: #1e293b;
  color: #f8fafc;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  pointer-events: none;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.2);
}
</style>
