<template>
  <div>
    <div ref="viewport" class="table-container" @scroll="syncFromTable">
      <slot />
    </div>
    <Teleport to="body">
      <div
        v-show="showFloatingBar"
        ref="floatingBar"
        class="floating-table-scrollbar"
        :style="{ left: `${barLeft}px`, width: `${barWidth}px` }"
        role="region"
        aria-label="表格横向滚动"
        tabindex="0"
        @scroll="syncFromBar"
      >
        <div :style="{ width: `${contentWidth}px`, height: '1px' }" />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const viewport = ref(null)
const floatingBar = ref(null)
const showFloatingBar = ref(false)
const barLeft = ref(0)
const barWidth = ref(0)
const contentWidth = ref(0)
let resizeObserver

const updateBar = () => {
  const table = viewport.value
  if (!table) return

  const bounds = table.getBoundingClientRect()
  contentWidth.value = table.scrollWidth
  barLeft.value = bounds.left
  barWidth.value = bounds.width
  showFloatingBar.value = table.scrollWidth > table.clientWidth + 1
    && bounds.top < window.innerHeight
    && bounds.bottom > window.innerHeight + 2

  if (floatingBar.value) floatingBar.value.scrollLeft = table.scrollLeft
}

const syncFromTable = () => {
  if (viewport.value && floatingBar.value) {
    floatingBar.value.scrollLeft = viewport.value.scrollLeft
  }
}

const syncFromBar = () => {
  if (viewport.value && floatingBar.value) {
    viewport.value.scrollLeft = floatingBar.value.scrollLeft
  }
}

const scrollToStart = () => {
  if (!viewport.value) return
  viewport.value.scrollLeft = 0
  const top = window.scrollY + viewport.value.getBoundingClientRect().top - 16
  window.scrollTo({ top, behavior: 'smooth' })
}

defineExpose({ scrollToStart })

onMounted(async () => {
  await nextTick()
  updateBar()
  window.addEventListener('scroll', updateBar, { passive: true })
  window.addEventListener('resize', updateBar)

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(updateBar)
    resizeObserver.observe(viewport.value)
    const table = viewport.value.querySelector('table')
    if (table) resizeObserver.observe(table)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateBar)
  window.removeEventListener('resize', updateBar)
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.floating-table-scrollbar {
  position: fixed;
  bottom: 0;
  height: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  z-index: 30;
  background: var(--card-bg);
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.42) transparent;
}

.floating-table-scrollbar:hover { scrollbar-color: rgba(148, 163, 184, 0.68) transparent; }
.floating-table-scrollbar::-webkit-scrollbar { height: 6px; }
.floating-table-scrollbar::-webkit-scrollbar-track { background: transparent; }
.floating-table-scrollbar::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.42); border-radius: 999px; }
.floating-table-scrollbar:hover::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.68); }
</style>
