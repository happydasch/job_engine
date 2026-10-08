<template>
  <div class="app-tabs" :class="{ 'app-tabs--compact': compact }" role="tablist">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      role="tab"
      :aria-selected="modelValue === tab.key"
      class="app-tab"
      :class="{ 'is-active': modelValue === tab.key }"
      @click="$emit('update:modelValue', tab.key)"
    >
      {{ tab.label }}
    </button>
    <slot name="suffix" />
  </div>
</template>

<script setup>
/**
 * AppTabs — shared tab strip (v-model bound to the active key).
 *
 * Replaces the duplicated tab markup in ScrapersView and AiAnalysisPane.
 *
 * Usage:
 *   <AppTabs v-model="activeTab" :tabs="[{ key: 'runs', label: 'Runs' }]" />
 */
defineProps({
  tabs: { type: Array, required: true }, // [{ key, label }]
  modelValue: { type: String, required: true },
  // compact: equal-width, smaller tabs for narrow panes (e.g. AI analysis box)
  compact: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.app-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 1.5rem;
  border-bottom: 2px solid var(--color-border, #e2e8f0);
  position: relative; /* anchors absolutely-positioned slot content */
}
.app-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.625rem 1.25rem;
  border: none;
  background: none;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  color: var(--color-text-secondary, #64748b);
}
.app-tab:hover { color: var(--color-text, #1e293b); }
.app-tab.is-active {
  border-bottom-color: var(--color-primary, #2563eb);
  color: var(--color-primary, #2563eb);
}

/* compact variant — equal-width, smaller tabs for narrow panes */
.app-tabs--compact {
  margin-bottom: 0;
  border-bottom-width: 1px;
}
.app-tabs--compact .app-tab {
  flex: 1;
  justify-content: center;
  padding: 0.5rem 0.25rem;
  font-size: 0.75rem;
  margin-bottom: -1px;
  border-bottom-width: 2px;
}
.app-tabs--compact .app-tab.is-active { font-weight: 600; }
</style>
