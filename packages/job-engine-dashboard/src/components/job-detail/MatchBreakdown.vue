<template>
  <div class="match-breakdown">
    <h3 class="breakdown-header">Match Breakdown</h3>
    <div class="breakdown-grid">
      <div class="match-bar" v-for="dim in dimensions" :key="dim.key">
        <div class="dim-header">
          <span class="dim-label">{{ dim.label }}</span>
          <span class="dim-score">{{ dim.score }}%</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: dim.score + '%' }"></div>
        </div>
      </div>
    </div>
    <div v-if="skillGap.matched.length || skillGap.missing.length" class="skill-gap">
      <div v-if="skillGap.matched.length" class="gap-row">
        <span class="gap-label">You have</span>
        <span v-for="s in skillGap.matched" :key="s" class="gap-chip gap-chip--have">{{ s }}</span>
      </div>
      <div v-if="skillGap.missing.length" class="gap-row">
        <span class="gap-label">Missing</span>
        <span v-for="s in skillGap.missing" :key="s" class="gap-chip gap-chip--missing">{{ s }}</span>
      </div>
    </div>
    <div class="match-total">
      <span class="total-label">Total Match</span>
      <span class="total-score">{{ totalScore }}%</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ details: { type: Object, required: true } })

// Fallback only when the backend omits a dimension entirely.
// Must mirror WEIGHTS/DIMENSION_LABELS in skill_scorer.py (8 dimensions, sums to 1.0).
const FALLBACK_DIMENSIONS = [
  { key: 'skill_overlap', label: 'Skills', weight: 0.25 },
  { key: 'keyword_boost', label: 'Keywords', weight: 0.15 },
  { key: 'career_alignment', label: 'Career', weight: 0.15 },
  { key: 'behavioral_fit', label: 'Behavioral', weight: 0.13 },
  { key: 'rate_fit', label: 'Rate', weight: 0.12 },
  { key: 'location_fit', label: 'Location', weight: 0.08 },
  { key: 'category_fit', label: 'Category', weight: 0.08 },
  { key: 'experience_fit', label: 'Experience', weight: 0.04 },
]

const dimensions = computed(() => {
  const comps = props.details.components || {}
  return FALLBACK_DIMENSIONS.map(f => {
    const comp = comps[f.key]
    return {
      key: f.key,
      label: comp?.label || f.label,
      score: Math.round(comp?.score ?? 0),
      weight: comp?.weight ?? f.weight,
    }
  })
})

// Absent for excluded-company results and for jobs scored before skill_gap existed.
const skillGap = computed(() => props.details.skill_gap || { matched: [], missing: [] })

const totalScore = computed(() => Math.round(props.details.total_score || 0))
</script>

<style scoped>
.match-breakdown { margin-top: 1rem; }
.breakdown-header { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; color: var(--color-text-secondary, #64748b); margin: 0 0 0.375rem; }
.breakdown-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px 8px; }
.match-bar { min-width: 0; }
.dim-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px; }
.dim-label { font-size: 0.625rem; color: var(--color-text-secondary, #64748b); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dim-score { font-size: 0.625rem; font-weight: 700; flex-shrink: 0; margin-left: 4px; }
.bar-track { height: 4px; background: var(--color-border, #e2e8f0); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; background: var(--color-primary, #3b82f6); }
.skill-gap { margin-top: 0.5rem; display: flex; flex-direction: column; gap: 4px; }
.gap-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.gap-label { font-size: 0.625rem; color: var(--color-text-secondary, #64748b); margin-right: 2px; }
.gap-chip { font-size: 0.625rem; padding: 1px 6px; border-radius: 999px; border: 1px solid var(--color-border, #e2e8f0); }
.gap-chip--have { color: var(--color-success, #16a34a); }
.gap-chip--missing { color: var(--color-danger, #dc2626); }
.match-total { display: flex; justify-content: space-between; align-items: center; padding-top: 0.375rem; margin-top: 0.375rem; border-top: 1px solid var(--color-border, #e2e8f0); }
.total-label { font-size: 0.6875rem; font-weight: 600; }
.total-score { font-size: 0.875rem; font-weight: 700; color: var(--color-primary, #3b82f6); }
</style>