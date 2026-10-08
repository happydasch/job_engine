<template>
  <div class="run-history">
    <DataTable
      :columns="historyColumns"
      :rows="history"
      :loading="loading"
      :error="loadError"
      empty-title="No runs yet"
      empty-message="Run scrapers to see history here"
    >
      <template #cell-run_id="{ row }">
        <span class="cell-run-id" :title="row.run_id">{{ truncateId(row.run_id) }}</span>
      </template>
      <template #cell-started_at="{ row }">
        <span>{{ formatDateTime(row.started_at) }}</span>
      </template>
      <template #cell-duration="{ row }">
        <span>{{ formatSeconds(row.duration) }}</span>
      </template>
      <template #cell-scrapers="{ row }">
        <div class="scraper-summary" v-if="row.scraper_statuses && Object.keys(row.scraper_statuses).length">
          <span
            v-for="group in groupedStatuses(row.scraper_statuses)"
            :key="group.status"
            class="scraper-status-chip"
            :class="'chip-' + group.className"
            :title="group.tooltip"
          >
            <span class="chip-dot"></span>
            <span class="chip-count">{{ group.count }}</span>
          </span>
        </div>
        <span v-else>{{ formatScrapers(row.scrapers || row.total_scrapers) }}</span>
      </template>
      <template #cell-jobs_found="{ row }">
        <span>{{ row.total_jobs_found || row.jobs_found || row.job_count || '—' }}</span>
      </template>
      <template #cell-jobs_new="{ row }">
        <span>{{ row.total_jobs_new || row.jobs_new || '—' }}</span>
      </template>
      <template #cell-error="{ row }">
        <span class="cell-error" :title="row.error">{{ row.error ? truncateId(row.error, 40) : '—' }}</span>
      </template>
      <template #cell-issues="{ row }">
        <span class="issues-badge" :class="row.issues_count ? 'issues-some' : 'issues-none'">
          {{ row.issues_count || 0 }}
        </span>
      </template>
      <template #cell-status="{ row }">
        <span class="history-status" :class="statusClass(row)">{{ row.status || row.state }}</span>
      </template>
      <template #cell-logs="{ row }">
        <button class="logs-btn" @click="showLogModal = true; historyLogRunId = row.run_id">
          Logs
        </button>
      </template>
    </DataTable>

    <!-- Log viewer modal for the selected run -->
    <LogViewerModal
      :visible="showLogModal"
      :run-id="historyLogRunId || ''"
      @close="showLogModal = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useScraperStatusStore } from '../../stores/scraperStatus'
import { useDateTime } from '../../composables/useDateTime'
import DataTable from '../common/DataTable.vue'
import LogViewerModal from './LogViewerModal.vue'

const store = useScraperStatusStore()
const { history } = storeToRefs(store)
const loading = ref(false)
const loadError = ref('')

const showLogModal = ref(false)
const historyLogRunId = ref('')

const historyColumns = [
  { key: 'run_id', label: 'Run ID', class: 'td-nowrap' },
  { key: 'started_at', label: 'Started' },
  { key: 'duration', label: 'Duration' },
  { key: 'scrapers', label: 'Scrapers' },
  { key: 'jobs_found', label: 'Total Jobs' },
  { key: 'jobs_new', label: 'New Jobs' },
  { key: 'error', label: 'Error' },
  { key: 'issues', label: 'Issues' },
  { key: 'status', label: 'Status' },
  { key: 'logs', label: '' },
]

const { formatDateTime, formatDuration, formatSeconds } = useDateTime()

function formatScrapers(scrapers) {
  if (!scrapers) return '—'
  if (Array.isArray(scrapers)) return scrapers.join(', ') || '—'
  if (typeof scrapers === 'number') return String(scrapers)
  return String(scrapers)
}

function groupedStatuses(statuses) {
  if (!statuses || typeof statuses !== 'object') return []
  const groups = {}
  for (const [scraper, status] of Object.entries(statuses)) {
    const st = (typeof status === 'string' ? status : (status.status || '')).toLowerCase()
    let key, className
    if (st === 'success' || st === 'completed') { key = 'completed'; className = 'success' }
    else if (st === 'failed' || st === 'error') { key = 'failed'; className = 'failed' }
    else if (st === 'running' || st === 'in_progress') { key = 'running'; className = 'running' }
    else if (st === 'skipped' || st === 'cancelled' || st === 'canceled') { key = 'skipped'; className = 'skipped' }
    else { key = 'other'; className = 'neutral' }
    if (!groups[key]) groups[key] = { status: key, className, count: 0, scrapers: [] }
    groups[key].count++
    groups[key].scrapers.push(scraper)
  }
  for (const g of Object.values(groups)) {
    g.tooltip = g.scrapers.map(s => `${s}: ${statuses[s]}`).join('\n')
  }
  // Sort: completed first, then failed, then the rest
  const order = { completed: 0, failed: 1, running: 2, skipped: 3, other: 4 }
  return Object.values(groups).sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9))
}

function statusClass(run) {
  const s = (run.status || run.state || '').toLowerCase()
  if (s === 'completed' || s === 'success') return 'badge-completed'
  if (s === 'running' || s === 'in_progress') return 'badge-running'
  if (s === 'failed' || s === 'error') return 'badge-failed'
  if (s === 'cancelled' || s === 'canceled') return 'badge-cancelled'
  return 'badge-default'
}

function truncateId(id, max = 8) {
  if (!id) return '—'
  if (id.length <= max) return id
  return id.substring(0, max) + '…'
}

async function loadHistory() {
  loading.value = true
  loadError.value = ''
  try {
    await store.loadHistory()
  } catch (e) {
    loadError.value = e?.message || 'Failed to load run history'
  }
  loading.value = false
}

onMounted(() => {
  if (!store.history.length) loadHistory()
})

defineExpose({ loadHistory })
</script>

<style scoped>
.run-history { margin-top: 1.5rem; }
.cell-run-id { font-family: monospace; font-size: 0.75rem; color: var(--color-text-secondary, #64748b); max-width: 100px; overflow: hidden; text-overflow: ellipsis; }
.cell-error { max-width: 150px; overflow: hidden; text-overflow: ellipsis; font-size: 0.75rem; color: #991b1b; }
.history-status { padding: 0.125rem 0.5rem; border-radius: 10px; font-size: 0.71875rem; font-weight: 500; text-transform: capitalize; display: inline-block; }
.badge-completed { background: #dcfce7; color: #166534; }
.badge-running { background: #dbeafe; color: #1e40af; }
.badge-failed { background: #fef2f2; color: #991b1b; }
.badge-cancelled { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }
.badge-default { background: #f1f5f9; color: #475569; }
.loading, .empty { text-align: center; padding: 1.5rem; }

/* Issues count */
.issues-badge { padding: 0.125rem 0.5rem; border-radius: 10px; font-size: 0.71875rem; font-weight: 600; display: inline-block; }
.issues-some { background: #fef2f2; color: #991b1b; }
.issues-none { background: #f1f5f9; color: #94a3b8; }

/* Logs button */
.logs-btn {
  padding: 2px 10px;
  font-size: 0.71875rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary, #64748b);
  cursor: pointer;
}
.logs-btn:hover { background: var(--color-bg-hover, #f1f5f9); }

/* Scraper status summary — grouped chips */
.scraper-summary {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.scraper-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px 1px 5px;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: 600;
  white-space: nowrap;
  cursor: default;
}
.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.chip-success { background: #dcfce7; color: #166534; }
.chip-success .chip-dot { background: #16a34a; }
.chip-failed { background: #fef2f2; color: #991b1b; }
.chip-failed .chip-dot { background: #dc2626; }
.chip-running { background: #dbeafe; color: #1e40af; }
.chip-running .chip-dot { background: #2563eb; }
.chip-skipped { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }
.chip-skipped .chip-dot { background: #94a3b8; }
.chip-neutral { background: #f1f5f9; color: #475569; }
.chip-neutral .chip-dot { background: #94a3b8; }

/* ── Responsive: small screens ── */
@media (max-width: 768px) {
  .run-history {
    margin-top: 1rem;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .run-history :deep(table) { min-width: 640px; }
  .run-history :deep(.data-table-wrapper) { overflow-x: visible; }
}
</style>
