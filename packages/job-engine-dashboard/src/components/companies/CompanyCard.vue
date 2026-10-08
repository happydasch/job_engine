<template>
  <router-link :to="`/companies/${company.id}`" class="company-card" :class="{ 'has-applications': company.has_applications }">
    <div class="company-card-icon" :style="{ background: cardColor }">{{ initials }}</div>
    <div class="company-card-text">
      <div class="company-card-name">{{ company.name }}</div>
      <div class="company-card-subtitle">
        {{ company.job_count || 0 }} listing{{ company.job_count === 1 ? '' : 's' }}
        <span v-if="company.has_applications" class="applied-badge">Applied</span>
      </div>
    </div>
  </router-link>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ company: { type: Object, required: true } })

const initials = computed(() => {
  if (!props.company?.name) return ''
  return props.company.name.slice(0, 2).toUpperCase()
})

const cardColor = computed(() => {
  if (!props.company?.name) return '#3b82f6'
  const colors = ['#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#ec4899', '#f43f5e', '#ef4444', '#f97316', '#eab308', '#22c55e', '#14b8a6', '#06b6d4']
  let hash = 0
  for (let i = 0; i < props.company.name.length; i++) {
    hash = props.company.name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
})
</script>

<style scoped>
.company-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 0.875rem;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px;
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s, background 0.15s;
}
.company-card:hover {
  background: var(--gray-100, #f8fafc);
  border-color: #cbd5e1;
}

.company-card-icon {
  width: 44px; height: 44px; border-radius: 10px;
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 1rem; font-weight: 700; flex-shrink: 0;
}

.company-card-text { flex: 1; min-width: 0; }
.company-card-name {
  font-weight: 600; font-size: 0.875rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.company-card.has-applications {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.03);
}
.company-card.has-applications:hover {
  border-color: #16a34a;
  background: rgba(34, 197, 94, 0.06);
}
.applied-badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 20px;
  font-size: 0.65rem;
  font-weight: 600;
  background: rgba(34, 197, 94, 0.12);
  color: #16a34a;
  line-height: 1.5;
}

.company-card-subtitle {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.375rem;
  font-size: 0.75rem; color: var(--color-text-secondary, #64748b);
}
</style>
