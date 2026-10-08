<template>
  <div class="section-header">
    <component :is="tag" class="section-title">
      {{ title }}
      <span v-if="count !== null" class="count-badge">{{ count }}</span>
    </component>
    <slot />
    <div v-if="$slots.action" class="section-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  count: { type: Number, default: null },
  level: { type: String, default: 'h2' },
})

const show = computed(() => props.count !== null)

const tag = computed(() => {
  const valid = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
  return valid.includes(props.level) ? props.level : 'h2'
})
</script>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.section-title {
  margin: 0;
  font-weight: 500;
  font-size: 0.9375rem;
}
.section-action {
  margin-left: auto;
}
.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 22px;
  padding: 0 8px;
  border-radius: 11px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--color-primary-10, rgba(37, 99, 235, 0.1));
  color: var(--color-primary, #3b82f6);
  vertical-align: middle;
}
</style>