<template>
  <div class="filter-toggle-group-wrapper">
    <FilterLabel v-if="label" size="sm">{{ label }}</FilterLabel>
    <div class="filter-toggle-group">
      <BaseButton
        v-for="opt in options"
        :key="opt.value"
        toggle
        :class="{ active: isSelected(opt.value) }"
        @click="toggle(opt.value)"
      >
        {{ opt.label }}
        <span v-if="opt.count != null" class="toggle-count">{{ opt.count }}</span>
      </BaseButton>
    </div>
  </div>
</template>

<script setup>
import BaseButton from '../BaseButton.vue'
import FilterLabel from '../FilterLabel.vue'

const props = defineProps({
  label: { type: String, default: '' },
  options: { type: Array, required: true }, // { value, label, count? }
  modelValue: { type: [String, Set], required: true },
  multi: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

function isSelected(value) {
  if (props.multi) {
    return props.modelValue instanceof Set && props.modelValue.has(value)
  }
  return props.modelValue === value
}

function toggle(value) {
  if (props.multi) {
    const newSet = new Set(props.modelValue)
    if (newSet.has(value)) {
      newSet.delete(value)
    } else {
      newSet.add(value)
    }
    emit('update:modelValue', newSet)
  } else {
    emit('update:modelValue', props.modelValue === value ? '' : value)
  }
}
</script>

<style scoped>
.filter-toggle-group-wrapper {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.filter-toggle-group {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 3px;
}
.toggle-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  border-radius: 10px;
  font-size: 0.6875rem;
  font-weight: 600;
  background: rgba(0,0,0,0.08);
  padding: 0 0.25rem;
  margin-left: 0.125rem;
}
.btn--toggle.active :deep(.toggle-count) {
  background: rgba(255,255,255,0.2);
}
</style>