<template>
  <div class="scraper-panel">
    <!-- Badges row with Run/Full View buttons on the right -->
    <div class="badges-row">
      <div class="badge-list" v-if="groupedBadges.length">
        <span v-for="g in groupedBadges" :key="g.status" class="badge-chip" :class="'chip-' + g.className" :title="g.tooltip">
          <span class="chip-dot"></span>
          <span class="chip-count">{{ g.count }}</span>
        </span>
      </div>
      <span v-else-if="statusLoaded" class="no-scrapers-info">No scrapers loaded</span>
      <div class="badges-row-actions">
        <BaseButton variant="secondary" size="sm" @click="goToScrapers">
          Full View
        </BaseButton>
        <BaseButton v-if="!isRunning" variant="primary" size="sm" @click="handleRun">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Run
        </BaseButton>
        <BaseButton v-if="isRunning" variant="danger" size="sm" @click="handleCancel">
          ■ Stop
        </BaseButton>
      </div>
    </div>

    <!-- Progress bar (always visible, even at 0% when idle) -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: progress + '%' }"></div>
    </div>

    <!-- Status — below progress -->
    <div class="status-row">
      <span class="scraper-dot" :class="isRunning ? 'dot-running' : 'dot-idle'"></span>
      <span class="status-text">{{ statusText }}</span>
      <span class="status-time">{{ statusTime }}</span>
    </div>

    <!-- Action errors (failed run start/cancel) -->
    <div v-if="actionError" class="action-error">{{ actionError }}</div>

    <!-- Issues collected during the current/last run -->
    <div v-if="issues.length" class="issues-box">
      <div class="issues-title">Issues ({{ issues.length }})</div>
      <div v-for="(issue, i) in issues.slice(-3)" :key="i" class="issue-line" :class="'issue-' + issue.severity">
        <span class="issue-severity">{{ issue.severity === 'warning' ? 'WARN' : 'ERR' }}</span>
        <span v-if="issue.source" class="issue-source">{{ issue.source }}</span>
        <span class="issue-message">{{ issue.message }}</span>
      </div>
      <div v-if="issues.length > 3" class="issues-more">… and {{ issues.length - 3 }} more (see Full View)</div>
    </div>

    <!-- Run History — improved timeline for sidebar -->
    <div v-if="history.length" class="run-timeline">
      <div class="run-timeline-header">
        <span class="run-timeline-title">Run History</span>
        <span class="run-timeline-total">{{ runTotalJobs }} jobs · {{ history.length }} runs</span>
      </div>
      <div class="run-timeline-list">
        <div v-for="(run, i) in history" :key="run.run_id" class="run-timeline-row">
          <div class="run-timeline-bar">
            <div class="run-timeline-dot" :class="'run-timeline-dot--' + statusClass(run)"></div>
            <div v-if="i < history.length - 1" class="run-timeline-line"></div>
          </div>
          <div class="run-timeline-content">
            <div class="run-timeline-top">
              <span class="run-timeline-time">{{ timeAgo(run.started_at) }}</span>
              <span class="run-timeline-status" :class="'status-pill--' + statusClass(run)">{{ statusLabel(run) }}</span>
            </div>
            <div class="run-timeline-stats">
              <span class="run-timeline-stat">{{ run.jobs_found || 0 }} jobs</span>
              <span class="run-timeline-dot-sep">·</span>
              <span class="run-timeline-stat">{{ run.jobs_new || 0 }} new</span>
              <span class="run-timeline-dot-sep">·</span>
              <span class="run-timeline-stat">{{ formatSeconds(run.duration) }}</span>
            </div>
            <div class="run-timeline-scrapers" v-if="run.scrapers && run.scrapers.length">
              <span class="scraper-tag" v-for="s in run.scrapers.slice(0, 5)" :key="s">{{ s.replace('.com', '').replace('.it', '') }}</span>
              <span class="scraper-tag scraper-tag--more" v-if="run.scrapers.length > 5">+{{ run.scrapers.length - 5 }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <EmptyState v-else title="No runs yet">
      <template #icon>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
      </template>
    </EmptyState>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useScraperStatusStore } from '../../stores/scraperStatus'
import BaseButton from '../common/BaseButton.vue'
import EmptyState from '../common/EmptyState.vue'

const emit = defineEmits(['close'])
const router = useRouter()

function goToScrapers() {
  router.push('/scrapers')
  emit('close')
}

const store = useScraperStatusStore()
const { status, progress, isRunning, scraperBadges, history } = storeToRefs(store)

// Group scraper badges by status for compact display
const groupedBadges = computed(() => {
  const groups = {}
  for (const { scraper, status: st } of scraperBadges.value) {
    const s = (typeof st === 'string' ? st : (st?.status || '')).toLowerCase()
    let key, className
    if (s === 'success' || s === 'completed') { key = 'completed'; className = 'success' }
    else if (s === 'failed' || s === 'error') { key = 'failed'; className = 'failed' }
    else if (s === 'running' || s === 'in_progress') { key = 'running'; className = 'running' }
    else if (s === 'skipped' || s === 'cancelled' || s === 'canceled') { key = 'skipped'; className = 'skipped' }
    else { key = 'other'; className = 'neutral' }
    if (!groups[key]) groups[key] = { status: key, className, count: 0, names: [] }
    groups[key].count++
    groups[key].names.push(scraper)
  }
  for (const g of Object.values(groups)) {
    g.tooltip = g.names.map(n => `${n}: ${scraperBadges.value.find(b => b.scraper === n)?.status || 'unknown'}`).join('\n')
  }
  const order = { completed: 0, failed: 1, running: 2, skipped: 3, other: 4 }
  return Object.values(groups).sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9))
})

const scrapersCompleted = computed(() => status.value?.scrapers_completed || 0)
const scrapersTotal = computed(() => status.value?.scrapers_total || 0)
// True once the first status fetch has resolved (whether or not it found badges) —
// avoids flashing "No scrapers loaded" before the initial fetch completes.
const statusLoaded = computed(() => status.value !== null)

// Status text — dynamic
const statusText = computed(() => {
  if (isRunning.value) {
    return `Running — ${scrapersCompleted.value}/${scrapersTotal.value} scrapers`
  }
  const s = status.value
  if (!s) return 'Loading…'
  if (s.status === 'completed') return `Completed — ${s.jobs_found_total || 0} jobs found`
  if (s.status === 'failed') return `Failed`
  if (s.status === 'timed_out') return 'Timed Out'
  return 'Idle'
})

const statusTime = computed(() => {
  if (isRunning.value && status.value?.elapsed_seconds != null) {
    return `${status.value.elapsed_seconds}s`
  }
  if (status.value?.started_at) return timeAgo(status.value.started_at)
  return ''
})

// Errors from run/cancel actions and issues collected during the run
const runActionError = ref('')
const actionError = computed(() => runActionError.value)
const issues = computed(() => status.value?.issues || [])

// ── Run Trigger ──

async function handleRun() {
  runActionError.value = ''
  const result = await store.triggerRun()
  if (!result.success) runActionError.value = result.error
}

async function handleCancel() {
  runActionError.value = ''
  const result = await store.cancelRun()
  if (!result.success) runActionError.value = result.error
}

// ── Utilities ──

const runTotalJobs = computed(() => {
  return history.value.reduce((sum, r) => sum + (r.jobs_found || 0), 0)
})

function statusClass(run) {
  const s = (run.status || '').toLowerCase()
  if (s === 'completed' || s === 'success') return 'completed'
  if (s === 'running' || s === 'in_progress') return 'running'
  if (s === 'failed' || s === 'error') return 'failed'
  if (s === 'cancelled' || s === 'canceled') return 'cancelled'
  return 'pending'
}

function statusLabel(run) {
  const s = (run.status || '').toLowerCase()
  if (s === 'completed' || s === 'success') return 'Completed'
  if (s === 'running' || s === 'in_progress') return 'Running'
  if (s === 'failed' || s === 'error') return 'Failed'
  if (s === 'cancelled' || s === 'canceled') return 'Cancelled'
  return run.status || 'Pending'
}

import { useDateTime } from '../../composables/useDateTime'

const { timeAgo, formatSeconds } = useDateTime()

// ── Lifecycle ──

onMounted(() => {
  store.init()
})
</script>

<style scoped>
.scraper-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Badges row — badges on left, Run/Stop/Full View on right */
.badges-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.badge-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex: 1;
  min-width: 0;
}
.badges-row-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.no-scrapers-info {
	  flex: 1;
	  color: var(--muted, #94a3b8);
	  font-size: 0.85rem;
	  display: flex;
	  align-items: center;
	}

	/* Progress bar — always visible */
.progress-bar {
  height: 4px;
  background: var(--color-border, var(--border, #e2e8f0));
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #16a34a);
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* Status — below progress */
.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.scraper-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-running { background: #16a34a; animation: pulse 1.5s ease-in-out infinite; }
.dot-idle { background: var(--muted, #94a3b8); }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.status-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text, var(--text, #1e293b));
}
.status-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
}

/* Scraper status chips — grouped by status */
.badge-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.badge-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px 1px 4px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
  cursor: default;
}
.badge-chip .chip-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.badge-chip.chip-success { background: #dcfce7; color: #166534; }
.badge-chip.chip-success .chip-dot { background: #16a34a; }
.badge-chip.chip-failed { background: #fef2f2; color: #991b1b; }
.badge-chip.chip-failed .chip-dot { background: #dc2626; }
.badge-chip.chip-running { background: #dbeafe; color: #1e40af; }
.badge-chip.chip-running .chip-dot { background: #2563eb; }
.badge-chip.chip-skipped { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }
.badge-chip.chip-skipped .chip-dot { background: #94a3b8; }
.badge-chip.chip-neutral { background: #f1f5f9; color: #475569; }
.badge-chip.chip-neutral .chip-dot { background: #94a3b8; }
.badge-running {
  background: rgba(37, 99, 235, 0.1);
  color: #2563eb;
  animation: pulse 1.5s ease-in-out infinite;
}
.badge-pending {
  background: rgba(148, 163, 184, 0.15);
  color: var(--muted, #94a3b8);
}
.badge-failed {
  background: rgba(220, 38, 38, 0.1);
  color: #dc2626;
}

/* Action errors */
.action-error {
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(220, 38, 38, 0.08);
  color: #dc2626;
  font-size: 12px;
  word-break: break-word;
}

/* Issues collected during the run */
.issues-box {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--color-border, var(--border, #e2e8f0));
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.issues-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #dc2626;
}
.issue-line {
  display: flex;
  gap: 6px;
  font-size: 11px;
  align-items: baseline;
}
.issue-severity { font-weight: 700; font-size: 10px; flex-shrink: 0; }
.issue-error .issue-severity { color: #dc2626; }
.issue-warning .issue-severity { color: #d97706; }
.issue-source {
  font-family: monospace;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  flex-shrink: 0;
}
.issue-message {
  color: var(--color-text, var(--text, #1e293b));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.issues-more {
  font-size: 10px;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
}

/* Section title */
.section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  margin-top: 12px;
}

/* Run History — Timeline (spacious sidebar version) */
.run-timeline {
  display: flex;
  flex-direction: column;
  padding: 24px 0 0;
}
.run-timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-border, #f1f5f9);
}
.run-timeline-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text, var(--text, #1e293b));
}
.run-timeline-total {
  font-size: 11px;
  color: var(--color-text-secondary, var(--text-secondary, #94a3b8));
}
.run-timeline-list { display: flex; flex-direction: column; }
.run-timeline-row {
  display: flex;
  gap: 0.75rem;
  min-height: 52px;
  position: relative;
  padding: 0.5rem 0.5rem 0.5rem 0;
  border-radius: 8px;
  transition: background 0.15s;
}
.run-timeline-row:hover {
  background: var(--color-bg-hover, #f8fafc);
}
.run-timeline-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
  position: relative;
  padding-top: 2px;
}
.run-timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  z-index: 1;
  border: 2.5px solid;
  transition: all 0.2s;
}
.run-timeline-dot--completed {
  background: #16a34a;
  border-color: #16a34a;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.15);
}
.run-timeline-dot--running {
  background: #2563eb;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
  animation: pulse 1.5s ease-in-out infinite;
}
.run-timeline-dot--failed {
  background: #dc2626;
  border-color: #dc2626;
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.15);
}
.run-timeline-dot--cancelled {
  background: #94a3b8;
  border-color: #94a3b8;
}
.run-timeline-dot--pending {
  background: #e2e8f0;
  border-color: #cbd5e1;
}
.run-timeline-line {
  width: 2.5px;
  flex: 1;
  background: var(--color-border, #e2e8f0);
  min-height: 16px;
  border-radius: 1px;
}
.run-timeline-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  gap: 2px;
}
.run-timeline-top {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.run-timeline-time {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text, var(--text, #1e293b));
}
.run-timeline-status {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.status-pill--completed { background: #dcfce7; color: #166534; }
.status-pill--running { background: #dbeafe; color: #1e40af; }
.status-pill--failed { background: #fef2f2; color: #991b1b; }
.status-pill--cancelled { background: #f1f5f9; color: #64748b; }
.status-pill--pending { background: #f8fafc; color: #94a3b8; }
.run-timeline-stats {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 12px;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
}
.run-timeline-stat {
  font-weight: 500;
}
.run-timeline-dot-sep {
  color: var(--color-border, #cbd5e1);
  font-weight: 700;
}
.run-timeline-scrapers {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 3px;
}
.scraper-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--color-bg, #f1f5f9);
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  font-weight: 500;
  white-space: nowrap;
}
.scraper-tag--more {
  background: transparent;
  color: var(--color-text-secondary, var(--text-secondary, #94a3b8));
  font-weight: 600;
}

/* Utilities */
.text-muted { color: var(--color-text-secondary, var(--text-secondary, #64748b)); }
.text-sm { font-size: 12px; }

/* ── Responsive: small screens ── */
@media (max-width: 640px) {
  .badges-row { flex-direction: column; align-items: stretch; }
  .badges-row-actions { justify-content: flex-end; }
  .run-timeline-list { max-height: 240px; }
}
</style>