<template>
  <div class="pagination" v-if="totalPages > 1">
    <BaseButton toggle :disabled="page <= 1" @click="$emit('page-change', page - 1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg> Prev</BaseButton>
    <BaseButton
      v-for="p in displayedPages"
      :key="p"
      toggle
      :class="{ active: p === page }"
      @click="$emit('page-change', p)"
    >
      {{ p }}
    </BaseButton>
    <BaseButton toggle :disabled="page >= totalPages" @click="$emit('page-change', page + 1)">Next <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></BaseButton>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import BaseButton from '../common/BaseButton.vue'

const props = defineProps({
  page: { type: Number, required: true },
  total: { type: Number, required: true },
  perPage: { type: Number, default: 50 },
})

defineEmits(['page-change'])

const totalPages = computed(() => Math.ceil(props.total / props.perPage))

const displayedPages = computed(() => {
  const pages = []
  const tp = totalPages.value
  const cp = props.page
  const start = Math.max(1, cp - 2)
  const end = Math.min(tp, cp + 2)
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
})
</script>

<style scoped>
.pagination { display: flex; gap: 0.25rem; justify-content: center; margin-top: 1.5rem; }
/* Page buttons come from the global button system (buttons.css) via BaseButton. */
</style>