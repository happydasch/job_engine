<template>
  <span
    class="status-badge"
    :class="[badgeClass, { 'status-badge--clickable': clickable }]"
    @click="handleClick"
    role="button"
    :tabindex="clickable ? 0 : -1"
    @keydown.enter.prevent="handleClick"
    @keydown.space.prevent="handleClick"
  >
    {{ displayLabel }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: '' },
  // Optional explicit color variant — use for non-application statuses
  // (success | warning | danger | muted). Overrides the status class.
  variant: { type: String, default: '' },
  label: { type: String, default: '' }, // explicit label override
  clickable: { type: Boolean, default: false },
})

const emit = defineEmits(['click'])

const labels = {
  interested: 'Interested',
  applied: 'Applied',
  interviewing: 'Interviewing',
  interview: 'Interview',
  offer: 'Offer',
  accepted: 'Accepted',
  rejected: 'Rejected',
  archived: 'Archived',
  withdrawn: 'Withdrawn',
}

const displayLabel = computed(() => props.label || labels[props.status] || props.status)

const badgeClass = computed(() => props.variant ? `badge-${props.variant}` : props.status)

function handleClick(event) {
  if (props.clickable) {
    emit('click', event)
  }
}
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: capitalize;
  letter-spacing: 0.025em;
}
.status-badge--clickable {
  cursor: pointer;
  position: relative;
}
.status-badge--clickable:hover {
  filter: brightness(1.1);
  box-shadow: 0 0 0 2px rgba(0,0,0,0.12);
}
.interested { background: #f0f9ff; color: #0369a1; }
.applied { background: #eff6ff; color: #1d4ed8; }
.interviewing { background: #fefce8; color: #a16207; }
.interview { background: #fefce8; color: #a16207; }
.offer { background: #f0fdf4; color: #15803d; }
.accepted { background: #dcfce7; color: #166534; }
.rejected { background: #fef2f2; color: #dc2626; }
.archived { background: #f8fafc; color: #64748b; }
.withdrawn { background: #f3e5f5; color: #6a1b9a; }

/* Explicit color variants (non-application statuses) */
.badge-success { background: rgba(22,163,74,0.1); color: #16a34a; }
.badge-warning { background: rgba(245,158,11,0.1); color: #b45309; }
.badge-danger { background: rgba(239,68,68,0.1); color: #dc2626; }
.badge-muted { background: rgba(100,116,139,0.1); color: #64748b; }
</style>