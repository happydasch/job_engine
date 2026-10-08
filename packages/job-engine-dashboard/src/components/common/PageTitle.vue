<template>
  <div class="page-title-wrapper">
    <h1 class="page-title">
      {{ title }}
      <span v-if="count !== null" class="count-badge">{{ count }}</span>
      <small v-if="subtitle" class="page-subtitle">{{ subtitle }}</small>
    </h1>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: null },
  count: { type: Number, default: null },
})
</script>

<style scoped>
.page-title-wrapper {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0 0 1.25rem;
  color: var(--text, var(--color-text, #1e293b));
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
  margin-left: 8px;
}
.page-subtitle {
  font-weight: 400;
  font-size: 0.8125rem;
  color: var(--text-secondary, var(--color-text-secondary, #64748b));
  margin-left: 4px;
}
</style>