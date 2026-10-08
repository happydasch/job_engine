<template>
  <!-- Pill variant: small rectangular badge (used in compact rows) -->
  <div v-if="variant === 'pill'" class="score-badge" :class="pillClass">
    {{ displayScore }}%
  </div>
  <!-- Ring variant: SVG circle with score text (used in full job cards) -->
  <div v-else class="score-ring" :style="{ width: size + 'px', height: size + 'px' }">
    <svg width="48" height="48" viewBox="0 0 48 48">
      <circle class="score-ring-bg" cx="24" cy="24" r="20" />
      <circle
        class="score-ring-fill"
        :class="ringArcClass"
        cx="24" cy="24" r="20"
        stroke-dasharray="125.6"
        :stroke-dashoffset="dashOffset"
      />
    </svg>
    <span class="score-text" :class="ringArcClass">{{ displayScore }}%</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: Number, required: true },
  variant: { type: String, default: 'ring' },
  size: { type: Number, default: 48 },
})

const C = 2 * Math.PI * 20 // 125.6637 — circumference for r=20

const displayScore = computed(() => Math.round(props.score))

const clamped = computed(() => Math.min(100, Math.max(0, displayScore.value)))

const dashOffset = computed(() => (C - (C * clamped.value / 100)).toFixed(1))

const ringArcClass = computed(() => {
  const s = props.score
  if (s >= 75) return 'top'
  if (s >= 50) return 'high'
  if (s >= 25) return 'med'
  return 'low'
})

const pillClass = computed(() => {
  const s = props.score
  if (s >= 75) return 'score-top'
  if (s >= 50) return 'score-high'
  if (s >= 25) return 'score-med'
  return 'score-low'
})
</script>

<style scoped>
/* Score ring — SVG circle */
.score-ring {
  position: relative;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.score-ring svg {
  position: absolute;
  top: 0;
  left: 0;
}
.score-ring-bg {
  fill: none;
  stroke: #e2e8f0;
  stroke-width: 4;
}
.score-ring-fill {
  fill: none;
  stroke-width: 4;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.5s ease;
  transform: rotate(-90deg);
  transform-origin: 50% 50%;
}
.score-ring-fill.top { stroke: var(--score-top); }
.score-ring-fill.high { stroke: var(--score-high); }
.score-ring-fill.med { stroke: var(--score-med); }
.score-ring-fill.low { stroke: var(--score-low); }
.score-text {
  font-weight: 700;
  font-size: 14px;
  z-index: 1;
  color: var(--text);
}
.score-text.top { color: var(--score-top); }
.score-text.high { color: var(--score-high); }
.score-text.med { color: var(--score-med); }
.score-text.low { color: var(--score-low); }

/* Score pill — compact rectangular badge */
.score-badge {
  min-width: 36px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  color: white;
  flex-shrink: 0;
}
.score-top { background: var(--score-top); }
.score-high { background: var(--score-high); }
.score-med { background: var(--score-med); }
.score-low { background: var(--score-low); }
</style>
