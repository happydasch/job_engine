<template>
  <div class="stats-grid">
    <div
      v-for="c in cards"
      :key="c.label"
      class="stats-card"
      :class="[accented ? 'stats-' + c.variant : '']"
    >
      <div class="stats-stat" :class="'stats-' + c.variant">{{ c.value }}</div>
      <div class="stats-label">{{ c.label }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  cards: {
    type: Array,
    default: () => [],
    /** Each card: { label: string, value: string|number, variant: string }
     *  variant maps to CSS: success, warning, danger, primary, critical, high, medium, low, neutral */
  },
  accented: {
    type: Boolean,
    default: false,
    /** When true, renders a colored left accent bar on each card */
  },
})
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}

@media (max-width: 800px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 540px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 360px) {
  .stats-grid { grid-template-columns: 1fr; }
}

.stats-card {
  padding: 10px 12px;
  text-align: center;
  position: relative;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

/* Left accent bar (only when accented) */
.stats-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 3px;
  border-radius: 0 2px 2px 0;
  display: none;
}
.stats-card.stats-critical::before { display: block; background: #c62828; }
.stats-card.stats-high::before { display: block; background: #e65100; }
.stats-card.stats-medium::before { display: block; background: #f9a825; }
.stats-card.stats-low::before { display: block; background: #2e7d32; }
.stats-card.stats-neutral::before { display: block; background: var(--text-secondary); }
.stats-card.stats-success::before { display: block; background: var(--success); }
.stats-card.stats-primary::before { display: block; background: var(--primary); }
.stats-card.stats-danger::before { display: block; background: var(--danger); }
.stats-card.stats-warning::before { display: block; background: var(--warning); }

.stats-stat {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.2;
}

.stats-stat.stats-success { color: var(--success); }
.stats-stat.stats-warning { color: var(--warning); }
.stats-stat.stats-primary { color: var(--primary); }
.stats-stat.stats-danger { color: var(--danger); }
.stats-stat.stats-critical { color: #c62828; }
.stats-stat.stats-high { color: #e65100; }
.stats-stat.stats-medium { color: #f9a825; }
.stats-stat.stats-low { color: #2e7d32; }
.stats-stat.stats-neutral { color: var(--text); }

.stats-label {
  font-size: 10px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  color: var(--text-secondary);
  margin-top: 2px;
}
</style>