<template>
  <div class="filter-sort">
    <FilterLabel v-if="label">{{ label }}</FilterLabel>
    <select
      class="filter-sort-select"
      :value="modelValue"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option
        v-for="opt in options"
        :key="opt.value"
        :value="opt.value"
      >{{ opt.label }}</option>
    </select>
    <button
      v-if="showOrder"
      class="filter-sort-order"
      :title="order === 'asc' ? 'Ascending' : 'Descending'"
      @click="$emit('toggle-order')"
      type="button"
    >
      <svg v-if="order === 'asc'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
    </button>
  </div>
</template>

<script setup>
import FilterLabel from '../FilterLabel.vue'

defineProps({
  modelValue: { type: String, required: true },
  options: { type: Array, required: true }, // { value, label }
  label: { type: String, default: '' },
  showOrder: { type: Boolean, default: false },
  order: { type: String, default: 'asc' },
})

defineEmits(['update:modelValue', 'toggle-order'])
</script>

<style scoped>
.filter-sort {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.filter-sort-select {
  padding: 0.375rem 0.5rem;
  border: none;
  border-radius: 6px;
  font-size: 0.8125rem;
  background: transparent;
  color: var(--color-text, #1e293b);
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
}
.filter-sort-select:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
}
.filter-sort-order {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  color: var(--color-text, #1e293b);
}
.filter-sort-order:hover { background: #f1f5f9; }
</style>