<template>
  <Card class="filter-panel">
    <form @submit.prevent>
      <!-- Above slot: content above the main row (e.g. catalog sources) -->
      <div v-if="$slots.above" class="fp-above">
        <slot name="above" />
      </div>
      <!-- Main row: search + default slot + reset -->
      <div class="fp-main">
        <div class="fp-search-wrap">
          <svg
            v-if="showSearchIcon"
            class="fp-search-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          ><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            ref="inputEl"
            :value="modelValue"
            type="text"
            :placeholder="placeholder"
            class="fp-search-input"
            :class="{ 'with-icon': showSearchIcon }"
            @input="onInput"
          />
          <button
            v-if="modelValue"
            class="fp-clear"
            @click="onClear"
            title="Clear search"
            type="button"
          >&times;</button>
        </div>

        <slot name="default" />

        <button
          v-if="showReset && hasActiveFilters"
          class="fp-reset"
          type="button"
          @click="onReset"
        >Reset</button>
      </div>

      <div v-if="$slots.actions" class="fp-actions">
          <slot name="actions" />
        </div><!-- Below slot: status tabs, filter pills, etc. + advanced toggle -->
      <div v-if="$slots.below || $slots.advanced" class="fp-below">
        <slot name="below" />
        <button
          v-if="$slots.advanced"
          type="button"
          class="fp-advanced-toggle"
          :class="{ active: showAdvanced || hasAdvancedFilters }"
          @click="showAdvanced = !showAdvanced"
          style="margin-left: auto;"
        >
          <span class="fp-toggle-icon" :style="{ transform: showAdvanced ? 'rotate(90deg)' : '' }">▸</span>
          More Filters
        </button>
      </div>

      <!-- Advanced filters (collapsible) -->
      <div v-show="showAdvanced" class="fp-advanced">
        <slot name="advanced" />
      </div>
    </form>
  </Card>
</template>

<script setup>
import { ref, watch } from 'vue'
import Card from './Card.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Search...' },
  debounceMs: { type: Number, default: 300 },
  showSearchIcon: { type: Boolean, default: false },
  showReset: { type: Boolean, default: false },
  hasActiveFilters: { type: Boolean, default: false },
  hasAdvancedFilters: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'search', 'reset'])

const inputEl = ref(null)
const showAdvanced = ref(false)

// Auto-open advanced filters when there are pre-set values (e.g. from URL query params)
watch(() => props.hasAdvancedFilters, (val) => {
  if (val) showAdvanced.value = true
}, { immediate: true })
let debounceTimer = null

function onInput(e) {
  const val = e.target.value
  emit('update:modelValue', val)
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('search', val)
  }, props.debounceMs)
}

function onClear() {
  emit('update:modelValue', '')
  emit('search', '')
  inputEl.value?.focus()
}

function onReset() {
  emit('reset')
  inputEl.value?.focus()
}
</script>

<style scoped>
.filter-panel {
  padding: 16px 20px;
  margin-bottom: 1.5rem;
}
.filter-panel form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Above slot ── */
.fp-above {
  margin-bottom: 0.5rem;
}

/* ── Main row ── */
.fp-main {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.fp-search-wrap {
  position: relative;
  flex: 1;
  min-width: 200px;
}
.fp-search-icon {
  position: absolute;
  left: 0.625rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-secondary, #94a3b8);
  pointer-events: none;
}
.fp-search-input {
  width: 100%;
  padding: 0.625rem 2rem 0.625rem 0.75rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
  font-size: 0.875rem;
  background: var(--color-bg-card, #fff);
  color: var(--color-text, #1e293b);
  box-sizing: border-box;
}
.fp-search-input.with-icon {
  padding-left: 2rem;
}
.fp-search-input:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
}
.fp-search-input::placeholder {
  color: var(--color-text-secondary, #94a3b8);
}
.fp-clear {
  position: absolute;
  right: 0.375rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  font-size: 1.25rem;
  line-height: 1;
  color: #94a3b8;
  cursor: pointer;
  padding: 0.125rem 0.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fp-clear:hover {
  color: #475569;
}

/* ── Reset button ── */
.fp-reset {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
  background: var(--color-bg-card, #fff);
  font-size: 0.8125rem;
  cursor: pointer;
  color: var(--color-text, #1e293b);
  white-space: nowrap;
}
.fp-reset:hover {
  background: #f1f5f9;
}


/* ── Actions slot ── */
.fp-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-left: auto;
}
/* ── Below slot ── */
.fp-below {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

/* ── Advanced toggle ── */
.fp-advanced-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.75rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 0.8125rem;
  cursor: pointer;
  color: var(--color-text-secondary, #64748b);
  font-weight: 500;
}
.fp-advanced-toggle:hover {
  background: #f1f5f9;
  color: var(--color-text, #1e293b);
}
.fp-advanced-toggle.active {
  background: rgba(59, 130, 246, 0.08);
  color: var(--color-primary, #3b82f6);
}
.fp-toggle-icon {
  display: inline-block;
  transition: transform 0.15s ease;
  font-size: 0.75rem;
}

/* ── Advanced section ── */
.fp-advanced {
  border-top: 1px solid var(--color-border, #e2e8f0);
  padding-top: 0.75rem;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: flex-end;
}
</style>