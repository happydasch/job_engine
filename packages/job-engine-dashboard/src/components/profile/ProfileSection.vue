<template>
  <div class="section" :class="sectionClass">
    <div class="section-header">
      <h3 class="section-title">{{ title }}</h3>
      <div class="section-header-actions">
        <slot name="header-extra" />
        <span v-if="weight" class="weight-badge">{{ weight }}</span>
      </div>
    </div>
    <span v-if="description" class="section-desc">{{ description }}</span>
    <div class="section-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  weight: { type: String, default: '' },
  sectionClass: { type: String, default: '' },
})
</script>

<style scoped>
.section {
  border: 1px solid var(--color-border, var(--border, #e2e8f0));
  border-radius: 8px;
  overflow: hidden;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem 0;
  background: var(--color-bg-hover, var(--gray-100, #f1f5f9));
}
.section-title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text, var(--text, #1e293b));
  margin: 0;
  min-width: 0;
}
.section-header-actions {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-shrink: 0;
  margin-left: 0.5rem;
}
.section-desc {
  display: block;
  padding: 0.75rem 0.375rem;
  font-size: 0.625rem;
  line-height: 1.4;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  background: var(--color-bg-hover, var(--gray-100, #f1f5f9));
}
.weight-badge {
  display: inline-flex;
  align-items: center;
  font-size: 0.625rem;
  font-weight: 700;
  padding: 0.125rem 0.4375rem;
  border-radius: 4px;
  background: var(--color-primary-08, rgba(37, 99, 235, 0.08));
  color: var(--color-primary, var(--primary, #2563eb));
  line-height: 1.4;
  letter-spacing: 0.01em;
}
.section-body {
  padding: 0.625rem 0.75rem;
}
</style>