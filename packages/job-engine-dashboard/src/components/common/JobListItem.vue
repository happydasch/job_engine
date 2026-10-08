<template>
  <router-link
    class="job-list-item"
    :to="'/jobs/' + encodeURIComponent(job.external_id)"
    :class="{ 'job-list-item--compact': compact }"
  >
    <ScoreBadge :score="job.match_score || 0" variant="pill" />
    <div class="job-list-item__body">
      <div class="job-list-item__title">{{ job.title }}</div>
      <div class="job-list-item__meta">
        <span class="job-list-item__company">{{ job.company || 'Unknown company' }}</span>
        <span class="job-list-item__sep">&middot;</span>
        <span class="job-list-item__platform">{{ formatPlatform(job.platform) }}</span>
        <template v-if="showLocation">
          <span class="job-list-item__sep">&middot;</span>
          <span v-if="job.remote" class="job-list-item__badge job-list-item__badge--remote">Remote</span>
          <span v-else class="job-list-item__location">{{ job.location || 'Unknown location' }}</span>
        </template>
      </div>
    </div>
  </router-link>
</template>

<script setup>
import ScoreBadge from './ScoreBadge.vue'

const props = defineProps({
  job: { type: Object, required: true },
  compact: { type: Boolean, default: false },
  showLocation: { type: Boolean, default: true },
})

function formatPlatform(p) {
  if (!p) return '?'
  return p.replace(/\.(com|it|co|uk|pl)$/, '')
}
</script>

<style scoped>
.job-list-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid var(--color-border-light, #f1f5f9);
  text-decoration: none;
  transition: background 0.12s ease;
}
.job-list-item:last-child {
  border-bottom: none;
}
.job-list-item:hover {
  background: var(--color-bg-hover, #f8fafc);
}

/* ── Compact variant (for dashboard sections) ── */
.job-list-item--compact {
  padding: 0.35rem 0.65rem;
}

/* ── Body ── */
.job-list-item__body {
  flex: 1;
  min-width: 0;
}

/* ── Title: single line, no wrap, ellipsis ── */
.job-list-item__title {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}
.job-list-item:hover .job-list-item__title {
  color: var(--color-primary, #3b82f6);
}

/* ── Meta row ── */
.job-list-item__meta {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #64748b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}

.job-list-item__company {
  font-weight: 500;
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.job-list-item__platform {
  flex-shrink: 0;
}

.job-list-item__sep {
  flex-shrink: 0;
  color: var(--color-text-tertiary, #cbd5e1);
}

.job-list-item__location {
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.job-list-item__badge--remote {
  display: inline-block;
  font-size: 0.6875rem;
  padding: 0.0625rem 0.3125rem;
  border-radius: 4px;
  background: var(--success-10, #ecfdf5);
  color: var(--success, #059669);
  font-weight: 500;
  flex-shrink: 0;
  line-height: 1.3;
}
</style>