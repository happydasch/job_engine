<template>
  <span class="job-fav-hide-buttons">
    <button
      type="button"
      class="btn-fav"
      :class="{ favorited: job.favorite }"
      :data-job-id="job.external_id"
      :data-favorited="String(!!job.favorite)"
      :title="job.favorite ? 'Remove from favorites' : 'Add to favorites'"
      :aria-label="job.favorite ? 'Remove from favorites' : 'Add to favorites'"
      :aria-pressed="!!job.favorite"
      :disabled="disabled"
      @click="$emit('toggle-fav', job.external_id)"
    ><AppIcon name="star" :filled="!!job.favorite" /></button>
    <button
      type="button"
      class="btn-hide"
      :class="{ 'hidden-state': job.hidden }"
      :data-job-id="job.external_id"
      :data-hidden="String(!!job.hidden)"
      :title="job.hidden ? 'Unhide job' : 'Hide job'"
      :aria-label="job.hidden ? 'Unhide job' : 'Hide job'"
      :aria-pressed="!!job.hidden"
      :disabled="disabled"
      @click="$emit('toggle-hide', job.external_id)"
    ><AppIcon name="x" /></button>
  </span>
</template>

<script setup>
/**
 * JobFavHideButtons — shared favorite/hide icon buttons for a job.
 *
 * Replaces the raw .btn-fav/.btn-hide buttons previously duplicated in
 * JobCard and JobDetailView (with different glyphs and styles).
 */
import AppIcon from '../common/AppIcon.vue'

defineProps({
  job: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
})
defineEmits(['toggle-fav', 'toggle-hide'])
</script>

<style scoped>
.job-fav-hide-buttons {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.btn-fav,
.btn-hide {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 4px;
  padding: 3px 0;
  cursor: pointer;
  color: var(--text-secondary, #64748b);
  transition: all 0.15s;
  min-width: 28px;
  text-align: center;
}
.btn-fav:hover,
.btn-hide:hover {
  background: var(--bg, #f8f9fa);
  border-color: var(--text-secondary, #64748b);
  color: var(--text, #1e293b);
}
.btn-fav:disabled,
.btn-hide:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-fav.favorited {
  color: var(--color-favorite, #d97706);
  border-color: var(--warning, #f59e0b);
  background: #fefce8;
}
.btn-hide.hidden-state {
  color: var(--text, #1e293b);
  border-color: var(--text-secondary, #64748b);
  background: var(--bg, #f8f9fa);
}
</style>
