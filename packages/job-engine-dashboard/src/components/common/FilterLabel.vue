<template>
  <span class="filter-label" :class="[sizeClass]"><slot /></span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  size: { type: String, default: 'md', validator: v => ['sm', 'md'].includes(v) },
})

const sizeClass = computed(() => `filter-label--${props.size}`)
</script>

<style scoped>
.filter-label {
  color: var(--color-text-secondary, #64748b);
  white-space: nowrap;
}
.filter-label--sm {
  font-size: 0.6875rem;
  letter-spacing: 0.05em;
}
.filter-label--md {
  font-size: 0.8125rem;
}
</style>