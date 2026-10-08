<template>
  <div v-if="loading" class="empty-state empty-state--loading" role="status" aria-busy="true">
    <span class="empty-state-spinner" aria-hidden="true"></span>
    <p class="empty-state-desc">{{ message || 'Loading...' }}</p>
  </div>
  <div v-else class="empty-state">
    <div v-if="$slots.icon" class="empty-state-icon">
      <slot name="icon" />
    </div>
    <h3 class="empty-state-title">{{ title }}</h3>
    <p v-if="message" class="empty-state-desc">{{ message }}</p>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  message: { type: String, default: '' },
  // loading variant: spinner + message, announced politely to screen readers
  loading: { type: Boolean, default: false },
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  text-align: center;
}
.empty-state-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: var(--color-bg-secondary, #f8fafc);
  color: var(--color-text-secondary, #64748b);
  margin-bottom: 1rem;
}
.empty-state-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text, #1e293b);
  margin: 0 0 0.5rem;
}
.empty-state-desc {
  color: var(--color-text-secondary, #64748b);
  margin: 0;
  max-width: 400px;
  line-height: 1.5;
}

/* loading variant */
.empty-state--loading { gap: 0.75rem; }
.empty-state-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--color-border, #e2e8f0);
  border-top-color: var(--color-primary, #2563eb);
  border-radius: 50%;
  animation: empty-state-spin 0.8s linear infinite;
}
@keyframes empty-state-spin {
  to { transform: rotate(360deg); }
}
</style>