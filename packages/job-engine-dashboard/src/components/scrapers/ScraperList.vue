<template>
  <div class="scraper-list">
    <div v-if="loading" class="loading">Loading scrapers...</div>
    <div v-else-if="!scrapers.length" class="empty">
      <EmptyState title="No scrapers installed" message="Install scrapers from the Catalog tab to get started">
        <router-link to="/scrapers?tab=catalog" class="step-action">Visit Catalog</router-link>
      </EmptyState>
    </div>
    <div v-else class="scraper-rows">
      <div
        v-for="p in scrapers"
        :key="p.id"
        class="scraper-row"
        :class="rowClasses(p)"
        :data-scraper-id="p.id"
      >
        <span class="last-run-dot" :class="'dot-' + (p.last_run_status || 'success')"></span>

        <span class="scraper-row-label-group">
          <span class="scraper-row-label">{{ p.label || p.name || p.id }}</span>
          <span class="scraper-row-status-line">
            <span v-if="p.last_run_at" class="scraper-row-last-run">
              {{ timeAgo(p.last_run_at) }} ·  {{ runJobCount(p.id) || "0" }} / {{ p.total_jobs }} jobs
            </span>
          </span>
        </span>

        <span class="scraper-row-actions">


          <BaseButton
            variant="ghost"
            icon
            size="sm"
            class="active"
            :disabled="isRunning || busyScraper === p.id"
            :loading="busyScraper === p.id"
            title="Run this scraper"
            @click="runScraper(p.id)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          </BaseButton>
          <BaseButton
            variant="ghost"
            icon
            dim
            :class="{ active: p.has_config }"
            :disabled="!p.has_config"
            :title="p.has_config ? 'Configure scraper' : 'No configurable options'"
            @click="p.has_config ? $emit('configure', p) : null"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </BaseButton>
          <BaseButton
            variant="soft-red"
            icon
            size="sm"
            title="Uninstall scraper"
            @click="uninstallScraper(p)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
          </BaseButton>
          <span
            class="scraper-row-switch"
            :class="{ active: p.enabled }"
            @click="toggleScraper(p.id, !p.enabled)"
          ></span>

        </span>
      </div>
    </div>
    <!-- Confirm Uninstall Modal -->
    <ConfirmModal
      :visible="showConfirm"
      title="Uninstall Scraper"
      :message="`Uninstall &quot;${pendingScraper?.name || pendingScraper?.id || ''}&quot;? The scraper will no longer be available for scraping`"
      confirm-text="Uninstall"
      confirm-variant="soft-red"
      @confirm="confirmUninstall"
      @cancel="cancelUninstall"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useScraperStatusStore } from '../../stores/scraperStatus'
import { useDateTime } from '../../composables/useDateTime'
import EmptyState from '../common/EmptyState.vue'
import BaseButton from '../common/BaseButton.vue'
import ConfirmModal from '../common/ConfirmModal.vue'
import { showToast } from '../../composables/useToast.js'

const props = defineProps({
  isRunning: { type: Boolean, default: false },
  status: { type: Object, default: null },
})
const emit = defineEmits(['run-scraper', 'refresh', 'configure', 'uninstall'])

const store = useScraperStatusStore()
const scrapers = computed(() => {
  const list = [...store.scrapers]
  list.sort((a, b) => {
    if (a.enabled === b.enabled) return 0
    return a.enabled ? -1 : 1
  })
  return list
})
const loading = computed(() => store.scrapersLoading)

// Confirm uninstall modal state
const showConfirm = ref(false)
const pendingScraper = ref(null)
const busyScraper = ref(null)
const { timeAgo } = useDateTime()


function runStatus(scraperId) {
  if (!props.status?.scraper_statuses) return null
  return props.status.scraper_statuses[scraperId] || null
}

function runJobCount(scraperId) {
  if (!props.status?.scraper_job_counts) return null
  const count = props.status.scraper_job_counts[scraperId]
  return count != null ? count : null
}

function rowClasses(p) {
  const run = runStatus(p.id)
  const classes = []
  if (p.enabled) classes.push('active')
  if (run) classes.push('row-' + run)
  return classes
}

async function runScraper(id) {
  busyScraper.value = id
  emit('run-scraper', id)
  // Reset busy after a short delay so the user sees the spinner
  // (the actual run status is tracked via the isRunning prop)
  setTimeout(() => { busyScraper.value = null }, 2000)
}

async function loadScrapers() {
  await store.loadScrapers()
}

function uninstallScraper(p) {
  pendingScraper.value = p
  showConfirm.value = true
}

function confirmUninstall() {
  showConfirm.value = false
  if (pendingScraper.value) {
    emit('uninstall', pendingScraper.value.id)
    pendingScraper.value = null
  }
}

function cancelUninstall() {
  showConfirm.value = false
  pendingScraper.value = null
}

async function toggleScraper(id, enabled) {
  try {
    const res = await fetch(`/api/scrape/scrapers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(body || `HTTP ${res.status}`)
    }
    const p = scrapers.value.find(x => x.id === id)
    if (p) p.enabled = enabled
    emit('refresh')
  } catch (e) {
    showToast(`Failed to ${enabled ? 'enable' : 'disable'} scraper: ${e.message}`, 'error')
  }
}

defineExpose({ loadScrapers })
onMounted(loadScrapers)
</script>

<style scoped>

/* Scraper rows as pills — grid with equal-width columns */
.scraper-rows {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: 8px;
}

.scraper-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px 3px 4px;
  border-radius: 999px;
  background: var(--color-bg-secondary, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
  transition: border-color 0.15s;
}
.scraper-row.active {
  border-color: var(--color-primary, #2563eb);
  background: rgba(37, 99, 235, 0.04);
}
/* ── Live scrape status row variants ── */
.scraper-row.row-running {
  border-color: #2563eb;
  background: rgba(37, 99, 235, 0.08);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.12);
  animation: row-pulse-blue 2s ease-in-out infinite;
}
.scraper-row.row-completed {
  border-color: #16a34a;
  background: rgba(22, 163, 74, 0.06);
}
.scraper-row.row-failed {
  border-color: #dc2626;
  background: rgba(220, 38, 38, 0.06);
}
.scraper-row.row-pending {
  border-color: #94a3b8;
  background: rgba(148, 163, 184, 0.06);
  opacity: 0.85;
}

@keyframes row-pulse-blue {
  0%, 100% { box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.12); }
  50% { box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.25); }
}

/* Scraper label + status stacked */
.scraper-row-label-group {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  margin-right: 8px;
}
.scraper-row-label {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text, #1e293b);
  cursor: pointer;
  line-height: 1.3;
}
.scraper-row-status-line {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.scraper-row-last-run {
  display: inline-flex;
  align-items: center;
  font-size: 9px;
  color: var(--color-text-secondary, #64748b);
  white-space: nowrap;
  line-height: 1.2;
}
.last-run-dot {
  width: 5px; height: 5px; border-radius: 50%; display: inline-block;
  margin: 0 4px;
  flex-shrink: 0;
}
.last-run-dot.dot-success { background: #16a34a; }
.last-run-dot.dot-failed { background: #dc2626; }
.last-run-dot.dot-partial { background: #f59e0b; }
.last-run-dot.dot-running { background: #2563eb; }

.scraper-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 1px;
}
.scraper-row-count {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 4px;
  border-radius: 6px;
  background: #f1f5f9;
  color: var(--color-text-secondary, #64748b);
  font-size: 9px;
  font-weight: 500;
}
.scraper-row-count svg {
  flex-shrink: 0;
}


/* Toggle switch — smaller for compact pills */
.scraper-row-switch {
  position: relative;
  width: 22px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 12px;
  background: #cbd5e1;
  cursor: pointer;
  transition: all 0.2s;
  margin-left: 4px;
}
.scraper-row-switch.active {
  background: var(--color-primary, #2563eb);
}
.scraper-row-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
}
.scraper-row-switch.active::after {
  transform: translateX(10px);
}

/* Buttons come from BaseButton.vue scoped styles. */

.loading, .empty { text-align: center; padding: 2rem; color: var(--color-text-secondary, #64748b); }
.empty-state-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
  justify-content: center;
}
.step-action {
  display: inline-flex;
  align-items: center;
  font-size: 0.75rem;
  font-weight: 500;
  color: #2563eb;
  text-decoration: none;
  padding: 0.3rem 0.65rem;
  border: 1px solid #2563eb;
  border-radius: 6px;
  transition: all 0.15s;
}
.step-action:hover {
  background: #2563eb;
  color: #fff;
}

/* ── Responsive: small screens ── */
@media (max-width: 640px) {
  .scraper-rows { grid-template-columns: 1fr; }
  .scraper-row { border-radius: 8px; padding: 6px 10px 6px 6px; }
  .scraper-row-label { font-size: 11px; }
  .scraper-row-status-line { flex-wrap: wrap; }
  .scraper-row-last-run { font-size: 8px; }
  .scraper-row-actions :deep(.base-button) { padding: 3px; }
  .scraper-row-actions :deep(.base-button svg) { width: 12px; height: 12px; }
}
</style>