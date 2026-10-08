<template>
  <div class="card" :class="{ 'card--flush': flush }">
    <slot />
  </div>
</template>

<script setup>
defineProps({
  flush: { type: Boolean, default: false }
})
</script>

<style>
/*
 * Intentionally UNSCOPED: Card is a layout primitive — its classes (.card,
 * .card--flush) are the sanctioned global card pattern used across all views.
 * Do not re-scope this block; scoped equivalents would break :deep() styling
 * of card content in parent views.
 */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 14px 20px;
}
.card--flush { overflow: hidden; }
</style>