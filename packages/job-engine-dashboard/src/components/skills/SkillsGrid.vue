<template>
  <div class="skill-gap-list">
    <div v-if="gaps.length" class="skills-grid">
      <div
        v-for="g in gaps"
        :key="g.skill"
        class="skill-card"
        :class="{ 'in-profile': g.in_profile }"
        @click="navigateToJobs(g.skill)"
      >
        <div class="skill-card-icon" :style="{ background: priorityColor(g.priority) }">
          {{ g.skill.slice(0, 2).toUpperCase() }}
        </div>
        <div class="skill-card-text">
          <div class="skill-card-name">
            <span class="skill-card-name-text">{{ g.skill }}</span>
          </div>
          <div class="skill-card-meta">
            <span class="meta-count">{{ g.frequency }} jobs</span>
            <span class="meta-match">{{ g.avg_match_score }}%</span>
          </div>
        </div>
        <div class="skill-card-actions">
          <button
            v-if="!g.in_profile && onAdd"
            class="skill-card-action-btn add-btn"
            title="Add skill to profile"
            @click.stop="onAdd(g.skill)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
          <button
            v-if="g.in_profile && onRemove"
            class="skill-card-action-btn remove-btn"
            title="Remove skill from profile"
            @click.stop="onRemove(g.skill)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
        </div>
      </div>
    </div>
    <EmptyState
      v-else
      title="No skills yet"
      message="Run scrapers first to populate skills"
    >
      <template #icon>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 6 9 17l-5-5"/>
        </svg>
      </template>
    </EmptyState>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import EmptyState from '../common/EmptyState.vue'

const props = defineProps({
  gaps: { type: Array, default: () => [] },
  onAdd: { type: Function, default: null },
  onRemove: { type: Function, default: null },
})

const router = useRouter()

function navigateToJobs(skill) {
  router.push(`/jobs?skill=${encodeURIComponent(skill)}`)
}

const priorityColors = {
  critical: '#dc2626',
  high: '#f97316',
  medium: '#eab308',
  low: '#94a3b8',
}

function priorityColor(priority) {
  return priorityColors[priority?.toLowerCase()] || '#94a3b8'
}
</script>

<style scoped>

.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}

.skill-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 0.875rem;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  min-width: 0;
  overflow: hidden;
  position: relative;
}
.skill-card:hover {
  background: var(--gray-100, #f8fafc);
  border-color: #cbd5e1;
}
.skill-card.in-profile {
  border-color: #22c55e;
  background: #22c55e08;
}


.skill-card-actions {
  display: flex;
  align-items: center;
  gap: 0.125rem;
  flex-shrink: 0;
  margin-left: auto;
  align-self: center;
}
.skill-card-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  background: transparent;
  transition: all 0.12s;
  padding: 0;
}
.skill-card-action-btn.add-btn {
  color: #15803d;
}
.skill-card-action-btn.add-btn:hover {
  background: rgba(21, 128, 61, 0.08);
  border-color: rgba(21, 128, 61, 0.3);
}
.skill-card-action-btn.remove-btn {
  color: #dc2626;
}
.skill-card-action-btn.remove-btn:hover {
  background: rgba(220, 38, 38, 0.08);
  border-color: rgba(220, 38, 38, 0.3);
}

.skill-card-icon {
  width: 44px; height: 44px; border-radius: 10px;
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 1rem; font-weight: 700; flex-shrink: 0;
}

.skill-card-text { flex: 1; min-width: 0; }
.skill-card-name {
  font-weight: 600;
  font-size: 0.875rem;
  line-height: 1.3;
  margin-bottom: 0.125rem;
  min-width: 0;
  overflow: hidden;
}
.skill-card-name-text {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0;
}

.skill-card-meta {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.1875rem 0.3125rem;
  font-size: 0.75rem;
}
.meta-count { color: var(--color-text-secondary, #64748b); }
.meta-match { color: var(--color-text-secondary, #64748b); }
</style>
