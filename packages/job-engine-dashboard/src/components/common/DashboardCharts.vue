<template>
  <div class="chart-grid">

    <!-- Match Score Distribution -->
    <div class="chart-card">
      <div class="chart-card-header">
        <div class="chart-card-title-row">
          <span class="chart-card-title">Match Score Distribution</span>
          <span class="chart-card-badge">{{ distTotal }} jobs</span>
        </div>
        <p class="chart-card-subtitle">How your profile scores against available jobs</p>
      </div>

      <EmptyState v-if="distTotal === 0" title="No job scores yet" />

      <div v-else class="dist-chart">
        <div class="dist-body">
          <div class="dist-rows">
            <div v-for="b in distBuckets" :key="b.cls" class="dist-row">
              <span class="dist-row-dot" :class="'dist-row-dot--' + b.cls"></span>
              <span class="dist-row-label">{{ b.label }}</span>
              <div class="dist-row-track">
                <div class="dist-row-bar" :class="'dist-row-bar--' + b.cls" :style="{ width: b.pct + '%' }"></div>
              </div>
              <span class="dist-row-count">{{ b.count }}</span>
              <span class="dist-row-pct">{{ b.pct }}%</span>
            </div>
          </div>

          <div class="dist-donut-wrapper">
            <div class="dist-donut" :style="{ background: donutGradient }">
              <div class="dist-donut-hole">
                <span class="dist-donut-val">{{ topBucket.pct }}%</span>
                <span class="dist-donut-label">{{ topBucket.cls }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Work Mode -->
    <div class="chart-card">
      <div class="chart-card-header">
        <div class="chart-card-title-row">
          <span class="chart-card-title">Work Mode</span>
          <span class="chart-card-badge">{{ remotePct }}% remote · {{ hybridPct }}% hybrid · {{ officePct }}% office</span>
        </div>
        <p class="chart-card-subtitle">Work location and contract types</p>
      </div>
      <div class="work-mode-content">
        <div class="mode-meter" title="Remote / Hybrid / Office split">
          <div v-if="remotePct > 0" class="mode-meter-seg mode-meter-seg--remote" :style="{ width: remotePct + '%' }">
            <span v-if="remotePct >= 20" class="mode-meter-label">{{ remotePct }}%</span>
          </div>
          <div v-if="hybridPct > 0" class="mode-meter-seg mode-meter-seg--hybrid" :style="{ width: hybridPct + '%' }">
            <span v-if="hybridPct >= 20" class="mode-meter-label">{{ hybridPct }}%</span>
          </div>
          <div v-if="officePct > 0" class="mode-meter-seg mode-meter-seg--office" :style="{ width: officePct + '%' }">
            <span v-if="officePct >= 20" class="mode-meter-label">{{ officePct }}%</span>
          </div>
        </div>
        <div class="mode-legend">
          <span class="mode-legend-item"><span class="mode-legend-dot mode-legend-dot--remote"></span> Remote</span>
          <span class="mode-legend-item"><span class="mode-legend-dot mode-legend-dot--hybrid"></span> Hybrid</span>
          <span class="mode-legend-item"><span class="mode-legend-dot mode-legend-dot--office"></span> Office</span>
        </div>

        <!-- Contracts -->
        <div class="work-mode-block">
          <div v-if="sortedContracts.length" class="mode-meter" title="Contract types">
            <div v-for="c in sortedContracts" :key="c[0]" class="mode-meter-seg" :class="'mode-meter-seg--contract-' + contractClass(c[0])" :style="{ width: contractPct(c, sortedContracts) + '%' }">
              <span v-if="contractPct(c, sortedContracts) >= 20" class="mode-meter-label">{{ contractPct(c, sortedContracts) }}%</span>
            </div>
          </div>
          <div v-if="sortedContracts.length" class="mode-legend">
            <span v-for="c in sortedContracts" :key="c[0]" class="mode-legend-item">
              <span class="mode-legend-dot" :class="'mode-legend-dot--contract-' + contractClass(c[0])"></span>
              {{ getContractLabel(c[0]) }}
            </span>
          </div>
          <span v-if="!sortedContracts.length" class="insight-empty">No data</span>
        </div>
      </div>
    </div>

    <!-- Score Breakdown -->
    <div class="chart-card">
      <div class="chart-card-header">
        <div class="chart-card-title-row">
          <span class="chart-card-title">Score Breakdown</span>
          <span class="chart-card-badge">{{ dimKeys.length }} dimensions</span>
        </div>
        <p class="chart-card-subtitle">Average score per matching dimension</p>
      </div>
      <EmptyState v-if="!dimKeys.length" title="No dimension data" />
      <div v-else class="dim-chart">
        <div v-for="key in dimKeys" :key="key" class="dim-row">
          <span class="dim-label">{{ dimLabels[key] || key }}</span>
          <div class="dim-track">
            <div class="dim-fill" :class="dimColor(key, avgDimensions[key])" :style="{ width: avgDimensions[key] + '%' }"></div>
          </div>
          <span class="dim-value">{{ avgDimensions[key] }}%</span>
          <span class="dim-weight">{{ dimWeights[key] }}%</span>
        </div>
      </div>
    </div>

    <!-- Application & Job Insights -->
    <div class="chart-card">
      <div class="chart-card-header">
        <div class="chart-card-title-row">
          <span class="chart-card-title">Application &amp; Job Insights</span>
          <span class="chart-card-badge">{{ totalJobs }} jobs</span>
        </div>
        <p class="chart-card-subtitle">Application funnel, job coverage, and enrichment</p>
      </div>

      <EmptyState v-if="totalJobs === 0" title="No job data yet" />

      <div v-else class="insights-content">

        <!-- Quick Stats -->
        <div class="insight-item">
          <div class="insight-stats">
            <div class="insight-stat">
              <span class="insight-stat-value">{{ platformCount }}</span>
              <span class="insight-stat-label">Platforms</span>
            </div>
            <div class="insight-stat">
              <span class="insight-stat-value">{{ totalJobs }}</span>
              <span class="insight-stat-label">Jobs found</span>
            </div>
            <div class="insight-stat">
              <span class="insight-stat-value">{{ appFunnel.applied }}</span>
              <span class="insight-stat-label">Applied</span>
            </div>
            <div class="insight-stat">
              <span class="insight-stat-value">{{ bestMatchScore }}%</span>
              <span class="insight-stat-label">Best match</span>
            </div>
          </div>
        </div>

        <!-- Application Funnel -->
        <div class="insight-item">
          <div class="insight-item-header">
            <span class="insight-item-title">Application Funnel</span>
            <span v-if="funnelTotal === 0" class="insight-item-badge-sm">No applications yet</span>
          </div>
          <div v-if="funnelTotal > 0" class="funnel-flow">
            <template v-for="(step, i) in funnelSteps" :key="step.key">
              <div class="funnel-step" :class="'funnel-step--' + step.key" :style="{ flex: funnelFlex(step) }">
                <span class="funnel-step-count">{{ step.count }}</span>
                <span class="funnel-step-label">{{ step.label }}</span>
              </div>
              <div v-if="i < funnelSteps.length - 1" class="funnel-cxn">
                <svg class="funnel-cxn-arrow" width="14" height="14" viewBox="0 0 16 16"><path d="M5 3l5 5-5 5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
                <span class="funnel-cxn-drop">{{ funnelDropOff(step, funnelSteps[i + 1]) }}%</span>
              </div>
            </template>
          </div>
        </div>

        <!-- LLM Enrichment -->
        <div class="insight-item">
          <div class="insight-item-header">
            <span class="insight-item-title">LLM Enrichment</span>
            <span class="insight-item-value">{{ llmPct }}%</span>
          </div>
          <div class="insight-item-bar">
            <div class="insight-item-bar-track">
              <div class="insight-item-bar-fill insight-item-bar-fill--llm" :style="{ width: llmPct + '%' }"></div>
            </div>
            <span class="insight-item-bar-label">{{ llmCount }} / {{ totalJobs }} jobs analyzed</span>
          </div>
        </div>

      </div>
    </div>

    <!-- Recent Scrapes -->
    <div class="chart-card">
      <div class="chart-card-header">
        <div class="chart-card-title-row">
          <span class="chart-card-title">Recent Scrapes</span>
          <span class="chart-card-badge">{{ jobsPerRun.length }} runs</span>
        </div>
      </div>

      <EmptyState v-if="!jobsPerRun.length" title="No runs yet" />

      <div v-else class="runs-list">
        <div v-for="(run, i) in jobsPerRun" :key="run.run_id" class="run-row" :class="{ 'run-row--latest': i === 0 }">
          <div v-if="i === 0 && latestChips.length" class="run-row-chips">
            <span v-for="s in latestChips" :key="s.name" class="chip">{{ s.name }} {{ s.count }}</span>
          </div>
          <div class="run-row-line">
            <span class="run-row-time">{{ timeAgo(run.started_at) }}</span>
            <span class="run-row-dot" :class="'run-row-dot--' + run.status" :title="run.status"></span>
            <div class="run-row-bar-track">
              <div v-if="run.jobs_new > 0" class="run-row-bar run-row-bar--new" :style="{ width: newJobsBarPct(run.jobs_new, run.jobs_found) + '%' }"></div>
            </div>
            <span class="run-row-jobs">{{ run.jobs_found }}<span v-if="run.jobs_new" class="run-row-new"> +{{ run.jobs_new }}</span></span>
            <span class="run-row-duration">{{ formatSeconds(run.duration) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Skills & Gaps -->
    <div class="chart-card">
      <div class="chart-card-header">
        <div class="chart-card-title-row">
          <span class="chart-card-title">Skills &amp; Gaps</span>
          <div class="chart-card-badges">
            <span class="chart-card-badge">{{ profileSkillsCount }} skills</span>
            <span v-if="criticalGaps.length" class="chart-card-badge chart-card-badge--warn">{{ criticalGaps.length }} gaps</span>
          </div>
        </div>
        <p class="chart-card-subtitle">In-demand skills and critical gaps in your profile</p>
      </div>

      <!-- Top Skills -->
      <div class="skills-gaps-section">
        <EmptyState v-if="!topSkills.length" title="No skills data" />
        <div v-else class="skills-chart">
          <div v-for="(s, i) in topSkills.slice(0, visibleRowCount)" :key="s.name" class="skill-row">
            <router-link :to="'/jobs?skill=' + s.name" class="skill-name-link">
              {{ s.name }}
            </router-link>
            <div class="skill-track">
              <div class="skill-fill" :style="{ width: skillBarPct(s.count) + '%' }"></div>
            </div>
            <span class="skill-count-val">{{ s.count }}</span>
          </div>
        </div>
      </div>

      <!-- Skill Gaps -->
      <div v-if="criticalGaps.length" class="skills-gaps-section">
        <div class="gaps-section">
          <div v-for="g in criticalGaps" :key="g.name" class="gap-row">
            <router-link :to="'/jobs?skill=' + g.name" class="gap-name">{{ g.name }}</router-link>
            <div class="gap-track">
              <div class="gap-fill" :style="{ width: gapPct(g.frequency) + '%' }"></div>
            </div>
            <span class="gap-freq">{{ g.frequency }}</span>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { getContractLabel } from '../../constants/enums.js'
import { useDateTime } from '../../composables/useDateTime'
import EmptyState from './EmptyState.vue'

const props = defineProps({
  matchDistBuckets: { type: Array, default: () => [] },
  topSkills: { type: Array, default: () => [] },
  profileSkillsCount: { type: Number, default: 0 },
  jobsPerRun: { type: Array, default: () => [] },
  remotePct: { type: Number, default: 0 },
  hybridPct: { type: Number, default: 0 },
  officePct: { type: Number, default: 0 },
  topPlatforms: { type: Array, default: () => [] },
  criticalGaps: { type: Array, default: () => [] },
  scheduler: { type: Object, default: () => ({ enabled: false, interval_minutes: 360 }) },
  totalJobs: { type: Number, default: 0 },
  platformCount: { type: Number, default: 0 },
  bestMatchScore: { type: Number, default: 0 },
  avgDimensions: { type: Object, default: () => ({}) },
  topContracts: { type: Array, default: () => [] },
  appFunnel: { type: Object, default: () => ({ applied: 0, interview: 0, offer: 0 }) },
  llmCount: { type: Number, default: 0 },
  scraperHealth: { type: Object, default: () => ({}) },
  section: { type: String, default: 'all', validator: v => ['all', 'top', 'bottom'].includes(v) },
})

// ── Match Score Distribution ────────────────────────────────────────────────

const visibleRowCount = 5

const distTotal = computed(() => props.matchDistBuckets.reduce((a, b) => a + b, 0))

const BUCKET_NAMES = ['--score-low', '--score-med', '--score-high', '--score-top']

const BUCKET_COLORS = computed(() => {
  if (typeof document === 'undefined') return ['#f97316', '#f59e0b', '#22c55e', '#3b82f6']
  const style = getComputedStyle(document.documentElement)
  return BUCKET_NAMES.map(name => (style.getPropertyValue(name) || '').trim() || '#999')
})

const distBuckets = computed(() => {
  const b = props.matchDistBuckets
  const total = distTotal.value || 1
  const labels = ['Low (0-25)', 'Med (25-50)', 'High (50-75)', 'Top (75-100)']
  const cls = ['low', 'med', 'high', 'top']
  return b
    .map((count, i) => ({ count, label: labels[i], cls: cls[i], color: BUCKET_COLORS.value[i], pct: Math.round((count / total) * 100) }))
})

const topBucket = computed(() => {
  const buckets = distBuckets.value
  return buckets.reduce((best, b) => (b.count > best.count ? b : best), buckets[0])
})

const donutGradient = computed(() => {
  // Build a conic-gradient from the non-zero buckets
  const buckets = distBuckets.value.filter(b => b.pct > 0)
  if (!buckets.length) return 'conic-gradient(#e2e8f0 0deg 360deg)'
  const parts = []
  let startDeg = 0
  for (const b of buckets) {
    const endDeg = startDeg + (b.pct / 100) * 360
    parts.push(`${b.color} ${startDeg}deg ${endDeg}deg`)
    startDeg = endDeg
  }
  return `conic-gradient(${parts.join(', ')})`
})

// ── Top Skills ──────────────────────────────────────────────────────────────

function capitalize(s) {
  if (!s) return s
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase()
}

function skillBarPct(count) {
  const max = props.topSkills[0]?.count || 1
  return Math.round((count / max) * 100)
}
// ── Recent Scrapes ────────────────────────────────────────────────────────────

const latestChips = computed(() => {
  const run = props.jobsPerRun?.[0]
  if (!run?.scraper_job_counts) return []
  return Object.entries(run.scraper_job_counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([name, count]) => ({
      name: name.replace('.com', '').replace('.it', ''),
      count,
    }))
})

// Each run row gets a full-width track bar. The track background is the bar
// itself. The blue "new jobs" overlay is proportional to each run's own ratio.
function newJobsBarPct(count, totalJobs) { return Math.round(((count || 0) / Math.max(totalJobs || 1, 1)) * 100) }

// ── Interesting Statistics ──────────────────────────────────────────────

function gapPct(freq) {
  const max = Math.max(...props.criticalGaps.map(g => g.frequency), 1)
  return Math.round((freq / max) * 100)
}

// ── State of Platform ───────────────────────────────────────────────────

const lastRunTime = computed(() => {
  const runs = props.jobsPerRun
  if (!runs?.length) return 'Never'
  return timeAgo(runs[0].started_at)
})
const { timeAgo, formatSeconds } = useDateTime()

// ── Score Breakdown ────────────────────────────────────────────────────

const DIM_LABELS = {
  skill_overlap: 'Skill Overlap',
  keyword_boost: 'Keyword Boost',
  location_fit: 'Location Fit',
  rate_fit: 'Rate Fit',
  category_fit: 'Category Fit',
  experience_fit: 'Experience Fit',
  behavioral_fit: 'Behavioral Fit',
  career_alignment: 'Career Alignment',
}

const DIM_WEIGHTS = {
  skill_overlap: 25,
  keyword_boost: 15,
  location_fit: 8,
  rate_fit: 12,
  category_fit: 8,
  experience_fit: 4,
  behavioral_fit: 13,
  career_alignment: 15,
}

const dimKeys = computed(() => Object.keys(props.avgDimensions))
const dimLabels = DIM_LABELS
const dimWeights = DIM_WEIGHTS

function dimColor(key, score) {
  if (score >= 70) return 'dim-fill--good'
  if (score >= 40) return 'dim-fill--mid'
  return 'dim-fill--low'
}

// ── Market Insights ────────────────────────────────────────────────────

const llmPct = computed(() => {
  return Math.round((props.llmCount / Math.max(props.totalJobs, 1)) * 100)
})

const funnelTotal = computed(() => {
  return props.appFunnel.applied + props.appFunnel.interview + props.appFunnel.offer
})

const funnelSteps = computed(() => {
  const steps = [
    { key: 'applied', label: 'Applied', count: props.appFunnel.applied },
    { key: 'interview', label: 'Interview', count: props.appFunnel.interview },
    { key: 'offer', label: 'Offer', count: props.appFunnel.offer },
  ]
  return steps
})

function funnelDropOff(prev, next) {
  if (prev.count === 0) return 0
  return Math.round(((prev.count - next.count) / prev.count) * 100)
}
function funnelFlex(step) {
  const maxCount = Math.max(...funnelSteps.value.map(s => s.count), 1)
  return maxCount > 0 ? (step.count / maxCount) : 1
}

function contractClass(type) {
  const t = (type || '').toLowerCase()
  if (t.includes('b2b') || t.includes('contract')) return 'b2b'
  if (t.includes('permanent') || t.includes('full')) return 'perm'
  if (t.includes('other')) return 'other'
  return 'other'
}

// Sort contracts: non-"other" types first (descending by count), then merge all "other"-classed into a single entry last
const sortedContracts = computed(() => {
  const arr = props.topContracts || []
  const known = []
  let otherSum = 0
  for (const [name, count] of arr) {
    if (contractClass(name) === 'other') {
      otherSum += count
    } else {
      known.push([name, count])
    }
  }
  known.sort((a, b) => b[1] - a[1])
  if (otherSum > 0) known.push(['Other', otherSum])
  return known
})

function contractPct(entry, all) {
  const total = all.reduce((sum, c) => sum + c[1], 0)
  return Math.round((entry[1] / Math.max(total, 1)) * 100)
}

// ── Scraper Health ─────────────────────────────────────────────────────

const scraperHealthKeys = computed(() => Object.keys(props.scraperHealth))

const scraperHealthyCount = computed(() => {
  return scraperHealthKeys.value.filter(k => {
    const s = props.scraperHealth[k]
    return s.success_rate >= 100 && s.last_status === 'success'
  }).length
})

const scraperIssueCount = computed(() => {
  return scraperHealthKeys.value.length - scraperHealthyCount.value
})

const scraperIssueKeys = computed(() => {
  return scraperHealthKeys.value.filter(k => {
    const s = props.scraperHealth[k]
    return s.success_rate < 100 || s.last_status !== 'success'
  })
})

const scraperAvgSuccess = computed(() => {
  const keys = scraperHealthKeys.value
  if (!keys.length) return 0
  const total = keys.reduce((sum, k) => sum + (props.scraperHealth[k].success_rate || 0), 0)
  return Math.round(total / keys.length)
})

const scraperOverallClass = computed(() => {
  if (scraperIssueCount.value === 0) return 'chart-card-badge--ok'
  return 'chart-card-badge--warn'
})
</script>

<style scoped>
/* ========================================================================
   Layout
   ======================================================================== */
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }

/* ========================================================================
   Card Base
   ======================================================================== */
.chart-card {
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px;
  padding: 1.25rem;
  overflow: hidden;
  min-width: 0;
}

.chart-card-badges { display: flex; gap: 0.375rem; align-items: center; }
.skills-gaps-section { margin-bottom: 0.75rem; }
.skills-gaps-section:last-child { margin-bottom: 0; }

.chart-card-header { margin-bottom: 1rem; }

.chart-card-title-row { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.chart-card-title { font-size: 0.875rem; font-weight: 600; color: var(--color-text, #1e293b); }
.chart-card-badge {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.1875rem 0.5rem;
  border-radius: 6px;
  background: var(--color-bg, #f1f5f9);
  color: var(--color-text-secondary, #64748b);
  white-space: nowrap;
}
.chart-card-subtitle { font-size: 0.75rem; color: var(--color-text-secondary, #64748b); margin-top: 0.125rem; }

/* ========================================================================
   Match Score Distribution — Donut + Breakdown Rows
   ======================================================================== */
.dist-chart { display: flex; flex-direction: column; gap: 0.5rem; }

.dist-body { display: flex; gap: 1rem; align-items: stretch; }
.dist-rows { flex: 1; display: flex; flex-direction: column; gap: 0.5rem; min-width: 0; }

.dist-row { display: flex; align-items: center; gap: 0.5rem; }
.dist-row-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dist-row-dot--low  { background: var(--score-low); }
.dist-row-dot--med  { background: var(--score-med); }
.dist-row-dot--high { background: var(--score-high); }
.dist-row-dot--top  { background: var(--score-top); }
.dist-row-label { font-size: 0.6875rem; font-weight: 600; min-width: 80px; color: var(--color-text, #1e293b); }
.dist-row-track { flex: 1; height: 10px; background: var(--color-bg, #f1f5f9); border-radius: 5px; overflow: hidden; }
.dist-row-bar {
  height: 100%; border-radius: 5px; transition: width 0.5s ease; min-width: 2px;
}
.dist-row-bar--low  { background: var(--score-low); }
.dist-row-bar--med  { background: var(--score-med); }
.dist-row-bar--high { background: var(--score-high); }
.dist-row-bar--top  { background: var(--score-top); }
.dist-row-count { font-size: 0.8125rem; font-weight: 700; min-width: 28px; text-align: right; color: var(--color-text, #1e293b); }
.dist-row-pct { font-size: 0.6875rem; font-weight: 500; color: var(--color-text-secondary, #64748b); min-width: 32px; }

/* ── Donut chart ── */
.dist-donut-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.dist-donut {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.dist-donut-hole {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: var(--color-bg-card, #fff);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.dist-donut-val {
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.1;
  color: var(--color-text, #1e293b);
}
.dist-donut-label {
  font-size: 0.5rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  color: var(--color-text-secondary, #64748b);
}

/* ========================================================================
   Top Skills Requested — Single-row per skill
   ======================================================================== */
.skills-chart { display: flex; flex-direction: column; gap: 0.5rem; }

.skill-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.skill-name-link {
  font-size: 0.78125rem;
  font-weight: 500;
  text-decoration: none;
  color: var(--color-text, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100px;
  flex-shrink: 0;
}
.skill-name-link:hover { color: var(--color-primary, #3b82f6); }
.skill-track {
  flex: 1;
  height: 10px;
  background: var(--color-bg, #f1f5f9);
  border-radius: 4px;
  overflow: hidden;
}
.skill-fill {
  height: 100%;
  border-radius: 4px;
  background: #3b82f6;
  transition: width 0.4s ease;
  min-width: 2px;
}
.skill-count-val {
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--color-text, #1e293b);
  flex-shrink: 0;
  width: 32px;
  text-align: right;
}

/* ========================================================================
   Recent Scrapes — compact single-line per run with bar
   ======================================================================== */
.runs-list { display: flex; flex-direction: column; gap: 1px; }

.run-row {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.71875rem;
}
.run-row--latest {
  background: var(--color-primary-light, #eff6ff);
}
.run-row-line {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.run-row-time {
  font-weight: 600;
  color: var(--color-text, #1e293b);
  min-width: 52px;
  flex-shrink: 0;
}
.run-row-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.run-row-dot--success { background: #16a34a; }
.run-row-dot--partial { background: #f59e0b; }
.run-row-dot--failed  { background: #dc2626; }

.run-row-bar-track {
  flex: 1;
  height: 10px;
  background: #cbd5e1;
  border-radius: 5px;
  overflow: hidden;
  position: relative;
  min-width: 60px;
}
.run-row-bar {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: 5px;
  transition: width 0.3s ease;
  min-width: 2px;
}
.run-row-bar--new { background: #3b82f6; z-index: 1; }

.run-row-jobs {
  color: var(--color-text, #1e293b);
  font-weight: 500;
  white-space: nowrap;
  width: 52px;
  flex-shrink: 0;
  text-align: right;
}
.run-row-new {
  color: var(--color-primary, #2563eb);
  font-weight: 600;
}

.run-row-duration {
  color: var(--color-text-secondary, #64748b);
  min-width: 36px;
  flex-shrink: 0;
}

.run-row-chips {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
  padding: 0.5rem 0;
}
.chip {
  font-size: 0.625rem;
  padding: 0.0625rem 0.3125rem;
  border-radius: 3px;
  background: #e2e8f0;
  color: #475569;
  white-space: nowrap;
}

/* ========================================================================
   Work Mode & Sources
   ======================================================================== */
.work-mode-content { display: flex; flex-direction: column; gap: 0.75rem; }
/* ── Segmented mode meter ── */
.mode-meter {
  display: flex;
  height: 28px;
  border-radius: 8px;
  overflow: hidden;
  cursor: help;
}
.mode-meter-seg {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: width 0.5s ease;
  min-width: 4px;
}
.mode-meter-seg--remote { background: #22c55e; }
.mode-meter-seg--hybrid { background: #f97316; }
.mode-meter-seg--office { background: var(--muted, #94a3b8); }
.mode-meter-label {
  font-size: 0.625rem;
  font-weight: 700;
  color: rgba(255,255,255,0.9);
  text-shadow: 0 1px 1px rgba(0,0,0,0.15);
  pointer-events: none;
}
.mode-legend {
  display: flex;
  gap: 1rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary, #64748b);
}
.mode-legend-item { display: flex; align-items: center; gap: 0.25rem; }
.mode-legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.mode-legend-dot--remote { background: #22c55e; }
.mode-legend-dot--hybrid { background: #f97316; }
.mode-legend-dot--office { background: var(--muted, #94a3b8); }

.work-mode-block { display: flex; flex-direction: column; gap: 0.375rem; }
.mode-meter-seg--contract-b2b { background: #3b82f6; }
.mode-meter-seg--contract-perm { background: #6366f1; }
.mode-meter-seg--contract-other { background: #94a3b8; }
.mode-legend-dot--contract-b2b { background: #3b82f6; }
.mode-legend-dot--contract-perm { background: #6366f1; }
.mode-legend-dot--contract-other { background: #94a3b8; }
/* ========================================================================
   Skill Gaps
   ======================================================================== */
.gaps-section { display: flex; flex-direction: column; gap: 0.5rem; }
.gaps-intro { font-size: 0.71875rem; color: var(--color-text-secondary, #64748b); margin-bottom: 0.25rem; line-height: 1.4; }
.gap-row { display: flex; align-items: center; gap: 0.5rem; }
.gap-name {
  font-size: 0.78125rem; font-weight: 500; text-decoration: none;
  color: var(--color-danger, #dc2626); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; width: 100px; flex-shrink: 0;
}
.gap-name:hover { color: var(--color-danger-hover, #b91c1c); text-decoration: underline; }
.gap-track { flex: 1; height: 10px; background: var(--color-bg, #f1f5f9); border-radius: 4px; overflow: hidden; }
.gap-fill { height: 100%; border-radius: 4px; background: var(--color-danger, #dc2626); transition: width 0.4s ease; min-width: 2px; }
.gap-freq { font-size: 0.8125rem; font-weight: 700; color: var(--color-text, #1e293b); flex-shrink: 0; width: 32px; text-align: right; }
.chart-card-badge--warn { background: #fef2f2; color: #dc2626; }

/* ========================================================================
   State of Platform
   ======================================================================== */
/* ========================================================================
   State of Platform — stat grid
   ======================================================================== */
.state-sched-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.1875rem 0.5rem;
  border-radius: 6px;
  white-space: nowrap;
}
.state-sched-badge--on {
  background: #f0fdf4;
  color: #16a34a;
}
.state-sched-badge--off {
  background: #f1f5f9;
  color: #64748b;
}
.state-sched-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.state-sched-badge--on .state-sched-dot {
  background: #16a34a;
  box-shadow: 0 0 3px rgba(22, 163, 74, 0.4);
}
.state-sched-badge--off .state-sched-dot {
  background: #94a3b8;
}
.platform-state-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
.platform-stat {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem 0.75rem;
  background: var(--color-bg, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
}
.platform-stat__icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.platform-stat__icon--jobs { background: #eff6ff; color: #3b82f6; }
.platform-stat__icon--platforms { background: #f0fdf4; color: #16a34a; }
.platform-stat__icon--score { background: #fefce8; color: #f59e0b; }
.platform-stat__icon--time { background: #f5f3ff; color: #8b5cf6; }
.platform-stat__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.platform-stat__value {
  font-size: 0.9375rem;
  font-weight: 700;
  color: var(--color-text, #1e293b);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.platform-stat__label {
  font-size: 0.6875rem;
  color: var(--color-text-secondary, #64748b);
  font-weight: 500;
  line-height: 1.2;
}

/* ========================================================================
   Score Breakdown — per-dimension averages
   ======================================================================== */
.dim-chart { display: flex; flex-direction: column; gap: 0.5rem; }
.dim-row { display: flex; align-items: center; gap: 0.5rem; }
.dim-label {
  font-size: 0.71875rem; font-weight: 500;
  color: var(--color-text, #1e293b);
  width: 96px; flex-shrink: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.dim-track { flex: 1; height: 10px; background: var(--color-bg, #f1f5f9); border-radius: 4px; overflow: hidden; }
.dim-fill { height: 100%; border-radius: 4px; transition: width 0.4s ease; min-width: 2px; }
.dim-fill--good { background: #1d4ed8; }
.dim-fill--mid { background: #3b82f6; }
.dim-fill--low { background: #93c5fd; }
.dim-value { font-size: 0.8125rem; font-weight: 700; color: var(--color-text, #1e293b); width: 36px; text-align: right; flex-shrink: 0; }
.dim-weight { font-size: 0.625rem; color: var(--color-text-secondary, #64748b); width: 28px; text-align: right; flex-shrink: 0; }

/* ========================================================================
   Job Insights — unified section without nested cards
   ======================================================================== */
.insights-content { display: flex; flex-direction: column; gap: 0.875rem; }

/* ── Quick stats row ── */
.insight-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; }
.insight-stat { display: flex; flex-direction: column; align-items: center; gap: 0.125rem; background: var(--color-bg, #f8fafc); border-radius: 6px; padding: 0.5rem 0.375rem; }
.insight-stat-value { font-size: 1rem; font-weight: 700; color: var(--color-text, #1e293b); line-height: 1.2; }
.insight-stat-label { font-size: 0.625rem; color: var(--color-text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.03em; }

.insight-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding-bottom: 0.875rem;
}
.insight-item-header {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.insight-item-title { font-size: 0.6875rem; font-weight: 600; color: var(--color-text, #1e293b); flex: 1; }
.insight-item-value { font-size: 0.8125rem; font-weight: 700; color: var(--color-text, #1e293b); }
.insight-item-badge-sm { font-size: 0.625rem; font-weight: 600; color: var(--color-text-secondary, #64748b); }
.insight-item-bar { display: flex; flex-direction: column; gap: 0.125rem; }
.insight-item-bar-track { height: 10px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
.insight-item-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
.insight-item-bar-fill--llm { background: #1d4ed8; }
.insight-item-bar-label { font-size: 0.625rem; color: var(--color-text-secondary, #64748b); }

/* ── Application Funnel — horizontal steps sized proportionally ── */
.funnel-flow { display: flex; align-items: center; gap: 0; margin-top: 6px; }
.funnel-step {
  display: flex; align-items: baseline; gap: 4px;
  padding: 5px 10px; border-radius: 8px;
  justify-content: center;
}
.funnel-step--applied { background: #1d4ed8; color: #fff; }
.funnel-step--interview { background: #3b82f6; color: #fff; }
.funnel-step--offer { background: #93c5fd; color: #1e3a5f; }
.funnel-step-count { font-size: 0.8125rem; font-weight: 700; }
.funnel-step-label { font-size: 0.625rem; font-weight: 600; }
.funnel-cxn {
  display: flex; align-items: center; gap: 2px;
  color: var(--color-text-secondary, #94a3b8);
  margin: 0 4px; flex-shrink: 0;
}
.funnel-cxn-arrow { flex-shrink: 0; }
.funnel-cxn-drop { font-size: 0.5625rem; font-weight: 600; white-space: nowrap; }

.insight-empty { font-size: 0.6875rem; color: var(--color-text-secondary, #64748b); font-style: italic; }

/* ========================================================================
   Scraper Health — compact summary + issues-only list
   ======================================================================== */
.sh-summary { display: flex; flex-direction: column; gap: 0.75rem; }
.sh-summary-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.375rem; }
.sh-summary-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.125rem;
  padding: 0.5rem 0.25rem;
  border-radius: 8px;
  background: var(--color-bg, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
}
.sh-summary-stat-value { font-size: 1rem; font-weight: 700; color: var(--color-text, #1e293b); line-height: 1.1; }
.sh-summary-stat-value--warn { color: #dc2626; }
.sh-summary-stat-label { font-size: 0.5625rem; font-weight: 600; color: var(--color-text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.03em; }
.sh-issues { display: flex; flex-direction: column; gap: 0.25rem; }
.sh-issue-row { display: flex; align-items: center; gap: 0.375rem; padding: 0.25rem 0.375rem; border-radius: 4px; }
.sh-issue-row:nth-child(odd) { background: var(--color-bg, #f8fafc); }
.sh-name { font-size: 0.6875rem; font-weight: 500; color: var(--color-text, #1e293b); min-width: 72px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sh-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.sh-dot--success { background: #16a34a; }
.sh-dot--partial { background: #f59e0b; }
.sh-dot--failed { background: #dc2626; }
.sh-track { flex: 1; height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
.sh-fill { height: 100%; border-radius: 4px; background: #3b82f6; transition: width 0.3s ease; }
.sh-rate { font-size: 0.6875rem; font-weight: 700; color: var(--color-text, #1e293b); width: 32px; text-align: right; flex-shrink: 0; }
.sh-runs { font-size: 0.625rem; color: var(--color-text-secondary, #64748b); width: 36px; text-align: right; flex-shrink: 0; }
.sh-all-healthy {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: #16a34a;
  padding: 0.5rem;
  background: #f0fdf4;
  border-radius: 6px;
}
.chart-card-badge--ok { background: #f0fdf4; color: #16a34a; }

/* ========================================================================
   Responsive
   ======================================================================== */
@media (max-width: 840px) {
  .chart-grid { grid-template-columns: 1fr; }
  .dist-row-label { min-width: 64px; }
  .dist-donut { width: 68px; height: 68px; }
  .dist-donut-hole { width: 42px; height: 42px; }
  .dist-donut-val { font-size: 0.875rem; }
}

@media (max-width: 640px) {
  .dist-row-label { min-width: 56px; font-size: 0.625rem; }
  .dist-row-count { font-size: 0.75rem; min-width: 22px; }
  .dist-row-pct { min-width: 28px; }
  .skill-name-link { font-size: 0.71875rem; width: 80px; }
  .skill-count-val { font-size: 0.75rem; }
  .mode-row { gap: 0.375rem; }
  .dist-donut { width: 60px; height: 60px; }
  .dist-donut-hole { width: 38px; height: 38px; }
  .dist-donut-val { font-size: 0.8125rem; }
}

@media (max-width: 480px) {
  .chart-card { padding: 1rem; }
  .dist-row-label { min-width: 44px; font-size: 0.5625rem; }
  .dist-row { gap: 0.25rem; }
  .skill-name-link { font-size: 0.6875rem; width: 64px; }
  .skill-count-val { font-size: 0.6875rem; }
  .skill-row { gap: 0.375rem; }
  .mode-label { min-width: 36px; font-size: 0.625rem; }
  .platform-pills { gap: 0.25rem; }
  .platform-pill { font-size: 0.625rem; padding: 0.1875rem 0.375rem; }
  .dist-donut { width: 52px; height: 52px; }
  .dist-donut-hole { width: 32px; height: 32px; }
  .dist-donut-val { font-size: 0.75rem; }
  .dist-donut-label { font-size: 0.4375rem; }
  .dist-body { gap: 0.625rem; }
}
</style>