<template>
  <div class="cat-editor">
    <div v-for="(cat, ci) in modelValue" :key="ci" class="cat-card">
      <div class="cat-card-header">
        <button v-if="!fixedCategories" class="cat-crit-toggle" :class="{ active: cat.critical }" :title="cat.critical ? 'Critical category' : 'Mark as critical'" @click="toggleCritical(ci)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        </button>
        <input v-if="!fixedCategories" v-model="cat.category" class="pf-input cat-name" type="text" :placeholder="catPlaceholder" />
        <span v-else class="cat-name cat-name-fixed">{{ cat.category }}</span>
        <BaseButton v-if="!fixedCategories" variant="ghost" size="xs" @click="remove(ci)" title="Remove">&times;</BaseButton>
      </div>
      <div class="cat-items">
        <div v-for="(item, ii) in cat.items" :key="ii" class="cat-item-tag" :class="{ 'cat-item-boosted': item.boosted }">
          <button v-if="!fixedCategories" class="cat-boost-toggle" :class="{ active: item.boosted }" :title="item.boosted ? 'Boosted keyword' : 'Mark as boosted'" @click="toggleBoosted(ci, ii)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          </button>
          <span class="cat-item-text">{{ item.name ?? item }}</span>
          <button class="cat-item-remove" @click="removeItem(ci, ii)">&times;</button>
        </div>
        <input
          class="pf-input cat-item-input"
          type="text"
          :placeholder="itemPlaceholder"
          @keydown.enter.prevent="addItem(ci, $event)"
        />
      </div>
    </div>
    <BaseButton v-if="!fixedCategories" variant="soft-blue" size="sm" @click="addCat">+ {{ addLabel }}</BaseButton>
  </div>
</template>

<script setup>
import BaseButton from '../common/BaseButton.vue'
const props = defineProps({
  modelValue: { type: Array, required: true },
  catPlaceholder: { type: String, default: 'Category name' },
  itemPlaceholder: { type: String, default: 'Add item + Enter' },
  addLabel: { type: String, default: 'Add Category' },
  fixedCategories: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

function addCat() {
  const next = [...props.modelValue, { category: '', critical: false, items: [] }]
  emit('update:modelValue', next)
}
function remove(i) {
  const next = props.modelValue.filter((_, idx) => idx !== i)
  emit('update:modelValue', next)
}
function removeItem(ci, ii) {
  const next = props.modelValue.map((cat, idx) => {
    if (idx !== ci) return cat
    return { ...cat, items: cat.items.filter((_, i) => i !== ii) }
  })
  emit('update:modelValue', next)
}
function addItem(ci, event) {
  const val = event.target.value.trim()
  if (!val) return
  const next = props.modelValue.map((cat, idx) => {
    if (idx !== ci) return cat
    return { ...cat, items: [...cat.items, { name: val, boosted: false }] }
  })
  emit('update:modelValue', next)
  event.target.value = ''
}
function toggleCritical(ci) {
  const next = props.modelValue.map((cat, idx) => {
    if (idx !== ci) return cat
    return { ...cat, critical: !cat.critical }
  })
  emit('update:modelValue', next)
}
function toggleBoosted(ci, ii) {
  const next = props.modelValue.map((cat, idx) => {
    if (idx !== ci) return cat
    return {
      ...cat,
      items: cat.items.map((item, i) => {
        if (i !== ii) return item
        return { ...item, boosted: !item.boosted }
      }),
    }
  })
  emit('update:modelValue', next)
}
</script>

<style scoped>
.cat-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cat-card {
  padding: 12px;
  background: var(--surface, #ffffff);
  border: 1px solid var(--color-border, var(--border, #e2e8f0));
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cat-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cat-name {
  flex: 1;
  font-weight: 500;
}
.cat-name-fixed {
  flex: 1;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  padding: 6px 0;
}
.cat-crit-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 3px;
  border-radius: 4px;
  color: var(--text-secondary, #94a3b8);
  transition: color 0.1s, background 0.1s;
  flex-shrink: 0;
}
.cat-crit-toggle:hover {
  background: rgba(245, 158, 11, 0.08);
  color: #d97706;
}
.cat-crit-toggle.active {
  color: #d97706;
}
.cat-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.cat-item-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 4px 8px 4px 4px;
  background: var(--color-primary-08, rgba(37, 99, 235, 0.08));
  color: var(--color-primary, var(--primary, #2563eb));
  border-radius: 6px;
  font-size: 0.71875rem;
  font-weight: 500;
  line-height: 1.4;
}
.cat-item-tag.cat-item-boosted {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}
.cat-boost-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 3px;
  color: var(--text-secondary, #94a3b8);
  transition: color 0.1s, background 0.1s;
}
.cat-boost-toggle:hover {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}
.cat-boost-toggle.active {
  color: #b45309;
}
.cat-item-text {
  line-height: 1.4;
}
.cat-item-remove {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  color: var(--text-secondary, #64748b);
  padding: 0 2px;
  display: flex;
  align-items: center;
  border-radius: 3px;
  transition: color 0.1s, background 0.1s;
}
.cat-item-remove:hover {
  color: var(--danger, #dc2626);
  background: rgba(220, 38, 38, 0.06);
}
.cat-item-input {
  min-width: 130px;
  flex: 0 1 auto;
  padding: 6px 10px;
  font-size: 0.71875rem;
}
.pf-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-family: inherit;
  font-size: 13px;
  background: var(--surface);
  color: var(--text);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.pf-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.pf-input::placeholder {
  color: var(--muted);
}
</style>