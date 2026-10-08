<template>
  <div class="scrapers-view">
    <PageTitle title="Scrapers" :count="pageTitleCount" />

    <AppTabs v-model="activeTab" :tabs="scraperTabs" />

    <div v-if="activeTab === 'runs'" class="runs-tab">
      <!-- Unified empty state when no scrapers installed -->
      <div v-if="!scraperCount" class="no-scrapers-empty">
        <EmptyState title="No scrapers installed" message="Install scrapers from the Catalog tab to get started">
          <router-link to="/scrapers?tab=catalog" class="empty-catalog-link">Visit Catalog</router-link>
        </EmptyState>
      </div>

      <template v-else>
        <Card class="scraper-card">

          <div class="scraper-header">

            <!-- Status row -->
            <div class="scraper-status-row">
              <span class="scraper-dot" :class="isRunning ? 'dot-running' : 'dot-idle'"></span>
              <span class="scraper-status-text">{{ isRunning ? 'Scraping in progress...' : 'Idle' }}</span>
              <span v-if="lastRun && !isRunning" class="scraper-last-run">Last run: {{ lastRun }}</span>
              <div v-if="isRunning" class="scraper-progress-track">
                <div class="scraper-progress-fill" :style="{ width: progress + '%' }"></div>
              </div>
              <BaseButton v-if="currentRunId" variant="secondary" size="sm" @click="showLogModal = true">View Logs</BaseButton>
            </div>

            <div class="scraper-actions">
              <div class="scraper-actions-right">
                <label class="auto-run-label" title="Auto-run scrapers periodically">
                  <input type="checkbox" v-model="autoRun" :disabled="saving" @change="saveSchedule" />
                  <span class="toggle-switch-sm"></span>
                  Auto
                </label>
                <div class="interval-badge-wrap">
                  <button type="button" class="interval-badge" @click="showIntervalDropdown = !showIntervalDropdown" title="Change auto-run interval" aria-haspopup="true" :aria-expanded="showIntervalDropdown">
                    {{ intervalMinutes }}m
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                  </button>
                  <div v-if="showIntervalDropdown" class="interval-dropdown" @click.stop>
                    <div class="interval-dropdown-body">
                      <label class="interval-dd-label">Interval (minutes):</label>
                      <input
                        type="number"
                        class="interval-dd-input"
                        v-model.number="intervalMinutes"
                        min="15"
                        max="43200"
                        step="15"
                      />
                      <div class="interval-dd-hint">min 15, max 43200 (30d)</div>
                      <div class="interval-dd-actions">
                        <BaseButton variant="secondary" size="xs" @click="showIntervalDropdown = false">Cancel</BaseButton>
                        <BaseButton variant="primary" size="xs" @click="saveSchedule(); showIntervalDropdown = false">Save</BaseButton>
                      </div>
                    </div>
                  </div>
                </div>
                <BaseButton v-if="!isRunning" variant="primary" @click="handleRun()">
                  <AppIcon name="play" filled />
                  Run
                </BaseButton>
                <BaseButton v-if="isRunning" variant="danger" @click="handleCancel()" aria-label="Stop scraping">
                  <AppIcon name="square" filled />
                  Stop
                </BaseButton>
              </div>
            </div>

            <!-- Issues from the current/last run -->
            <div v-if="issues.length" class="run-issues-box">
              <div class="run-issues-title">Issues ({{ issues.length }})</div>
              <div v-for="(issue, i) in issues" :key="i" class="run-issue-row" :class="'issue-' + issue.severity">
                <span class="issue-severity">{{ issue.severity }}</span>
                <span v-if="issue.source" class="issue-source">{{ issue.source }}</span>
                <span class="issue-message">{{ issue.message }}</span>
              </div>
            </div>

          </div>
        </Card>

        <div class="scraper-rows">

          <ScraperList
            :is-running="isRunning"
            :status="status"
            @run-scraper="triggerRun"
            @refresh="onScrapersChanged"
            @configure="openConfig"
            @uninstall="onUninstallScraper"
          />

        </div>

        <RunHistory />
      </template>
    </div>

    <div v-else class="catalog-tab">
      <ScraperCatalog
        ref="scraperCatalogRef"
        :is-running="isRunning"
        @installed="onScrapersChanged"
        @uninstalled="onScrapersChanged"
      />
    </div>

    <!-- Scraper Config Modal -->
    <ScraperConfigModal
      :visible="configModalVisible"
      :scraper="configScraper"
      @close="configModalVisible = false"
      @saved="onConfigSaved"
    />
    <!-- Log Viewer Modal -->
    <LogViewerModal
      :visible="showLogModal"
      :run-id="currentRunId || ''"
      @close="showLogModal = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useScraperStatusStore } from '../stores/scraperStatus'
import { showToast } from '../composables/useToast'
import { useDateTime } from '../composables/useDateTime'
import { useLocalStorage } from '../composables/useLocalStorage'
import ScraperList from '../components/scrapers/ScraperList.vue'
import RunHistory from '../components/scrapers/RunHistory.vue'
import LogViewerModal from '../components/scrapers/LogViewerModal.vue'
import PageTitle from '../components/common/PageTitle.vue'
import ScraperCatalog from '../components/scrapers/ScraperCatalog.vue'
import ScraperConfigModal from '../components/scrapers/ScraperConfigModal.vue'
import BaseButton from '../components/common/BaseButton.vue'
import Card from '../components/common/Card.vue'
import AppIcon from '../components/common/AppIcon.vue'
import AppTabs from '../components/common/AppTabs.vue'
import EmptyState from '../components/common/EmptyState.vue'

const route = useRoute()
const activeTab = useLocalStorage('job_engine_scrapers_active_tab', 'runs')
const scraperTabs = [
  { key: 'runs', label: 'Runs' },
  { key: 'catalog', label: 'Catalog' },
]
const scraperStatusStore = useScraperStatusStore()
const { status, isRunning, progress, history } = storeToRefs(scraperStatusStore)
const { triggerRun, cancelRun } = scraperStatusStore

// Issues collected during the current/last run
const issues = computed(() => status.value?.issues || [])
const currentRunId = computed(() => status.value?.run_id || null)
const showLogModal = ref(false)

async function handleRun() {
  const result = await triggerRun()
  if (!result.success) showToast(result.error || 'Failed to start run', 'error')
}

async function handleCancel() {
  const result = await cancelRun()
  if (!result.success) showToast(result.error || 'Failed to cancel run', 'error')
}

const { formatDateTime } = useDateTime()

const lastRun = computed(() => {
  const started = history.value[0]?.started_at
  if (!started) return ''
  return formatDateTime(started)
})

const scrapersSubtitle = computed(() => {
  if (isRunning.value) return 'Scraping in progress'
  return lastRun.value ? `Last run ${lastRun.value}` : 'Idle'
})

// ScraperCatalog ref
const scraperCatalogRef = ref(null)

// Page title count: show filtered catalog count on catalog tab, else runs tab count
const pageTitleCount = computed(() => {
  if (activeTab.value === 'catalog' && scraperCatalogRef.value) {
    const c = scraperCatalogRef.value.filteredCount
    return c != null ? `${c} available` : null
  }
  const c = scraperStatusStore.scrapers.filter(s => s.enabled).length
  return c ? `${c} enabled` : null
})

// Total scrapers count (for empty state check)
const scraperCount = computed(() => scraperStatusStore.scrapers.length)

// Config modal
const configModalVisible = ref(false)
const configScraper = ref(null)

// Schedule management
const autoRun = ref(false)
const intervalMinutes = ref(360)
const showIntervalDropdown = ref(false)

function onClickOutside(e) {
  if (showIntervalDropdown.value) {
    const wrap = e.target.closest('.interval-badge-wrap')
    if (!wrap) showIntervalDropdown.value = false
  }
}
onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))

async function loadSchedule() {
  try {
    const res = await fetch('/api/scrape/schedule')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    autoRun.value = !!data.auto_run
    intervalMinutes.value = data.interval_minutes ?? 360
  } catch (e) {
    console.error('Failed to load scraper schedule:', e)
  }
}

async function saveSchedule() {
  try {
    const res = await fetch('/api/scrape/schedule', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_run: autoRun.value, interval_minutes: intervalMinutes.value }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
  } catch (e) {
    showToast(`Failed to save schedule: ${e.message}`, 'error')
    // Re-sync the toggle with the persisted state
    loadSchedule()
  }
}

function openConfig(scraper) {
  configScraper.value = scraper
  configModalVisible.value = true
}

async function onConfigSaved() {
  configModalVisible.value = false
  configScraper.value = null
  scraperStatusStore.loadScrapers()
}

async function onScrapersChanged() {
  scraperStatusStore.loadScrapers()
}

async function onUninstallScraper(scraperId) {
  try {
    const res = await fetch(`/api/scrapers/catalog/uninstall/${scraperId}`, { method: 'POST' })
    if (res.ok) {
      showToast(`Uninstalled ${scraperId}`, 'success')
      scraperStatusStore.loadScrapers()
      // Refresh ScraperCatalog catalog if it's mounted
      if (scraperCatalogRef.value) {
        scraperCatalogRef.value.fetchCatalog()
      }
    } else {
      const err = await res.json()
      showToast(err.detail || 'Failed to uninstall', 'error')
    }
  } catch (e) {
    showToast(e.message, 'error')
  }
}

function syncTabFromQuery(tabParam) {
  if (tabParam === 'catalog' || tabParam === 'runs') {
    activeTab.value = tabParam
  }
}

// Vue Router reuses this view's instance when only the query changes
// (e.g. navigating from /scrapers to /scrapers?tab=catalog), so onMounted
// alone won't catch it — watch the query too.
watch(() => route.query.tab, syncTabFromQuery)

onMounted(() => {
  syncTabFromQuery(route.query.tab)
  scraperStatusStore.init()
  loadSchedule()
})
</script>

<style scoped>
.scrapers-view { }

/* Unified empty state when no scrapers installed */
.no-scrapers-empty {
  padding: 3rem 1rem;
  text-align: center;
}
.empty-catalog-link {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: #2563eb;
  text-decoration: none;
  padding: 0.45rem 0.9rem;
  border: 1px solid #2563eb;
  border-radius: 8px;
  transition: all 0.15s;
}
.empty-catalog-link:hover {
  background: #2563eb;
  color: #fff;
}

/* Scraper card — wraps header + body */
.scraper-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.scraper-title { font-size: 15px; font-weight: 600; color: var(--color-text, #1e293b); }
.scraper-status-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  flex: 1; min-width: 0;
}
.scraper-actions {
  display: flex; align-items: flex-start; gap: 8px;
  flex-shrink: 0; justify-content: flex-end;
}
.scraper-actions-left {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  flex: 1; min-width: 0;
}

/* Scraper rows fill the full width */
.scraper-rows {
  display: flex;
  flex-direction: column;
}
.scraper-rows :deep(.scraper-list) {
  width: 100%;
}
.scraper-rows :deep(.scraper-rows) {
  width: 100%;
}
.scraper-actions-right {
  display: flex; align-items: center; gap: 8px;
  flex-shrink: 0;
}
.auto-run-label {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 500;
  color: var(--color-text, #1e293b); cursor: pointer; user-select: none;
  background: var(--color-bg-secondary, #f8fafc); border: 1px solid var(--color-border, #e2e8f0);
  transition: border-color 0.15s, background 0.15s;
}
.auto-run-label:hover { border-color: var(--color-text-secondary, #64748b); }
.auto-run-label:has(input:checked) {
  background: rgba(37, 99, 235, 0.06); border-color: var(--color-primary, #2563eb);
  color: var(--color-primary, #2563eb);
}
.auto-run-label input { width: 0; height: 0; opacity: 0; position: absolute; pointer-events: none; }
.auto-run-label .toggle-switch-sm {
  position: relative; width: 18px; height: 10px; flex-shrink: 0;
  border-radius: 10px; background: #cbd5e1; transition: background 0.2s;
}
.auto-run-label:has(input:checked) .toggle-switch-sm { background: var(--color-primary, #2563eb); }
.auto-run-label .toggle-switch-sm::after {
  content: ''; position: absolute; top: 1.5px; left: 1.5px;
  width: 7px; height: 7px; border-radius: 50%; background: #fff;
  transition: transform 0.2s;
}
.auto-run-label:has(input:checked) .toggle-switch-sm::after { transform: translateX(8px); }

/* Interval badge — styled like a secondary button */
.interval-badge-wrap {
  position: relative; display: inline-flex;
}
.interval-badge {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 500;
  background: var(--color-bg-secondary, #f8fafc); border: 1px solid var(--color-border, #e2e8f0);
  color: var(--color-text-secondary, #64748b); font-family: inherit;
  cursor: pointer; user-select: none; transition: border-color 0.15s, background 0.15s, color 0.15s;
}
.interval-badge:hover {
  background: var(--color-bg, #f1f5f9); border-color: var(--color-text-secondary, #64748b);
  color: var(--color-text, #1e293b);
}
.interval-dropdown {
  position: absolute; top: 100%; right: 0; margin-top: 4px; z-index: 50;
  background: var(--color-bg-card, #fff); border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  min-width: 200px;
}
@media (max-width: 640px) {
  .scraper-header { flex-direction: column; align-items: stretch; }
  .scraper-status-row { flex: none; }
  .scraper-actions { width: 100%; justify-content: flex-start; }
  .scraper-actions-right { width: 100%; flex-wrap: wrap; justify-content: flex-start; }

  .scraper-progress-track { flex: none; width: 100%; min-width: unset; }
  .scraper-status-text { font-size: 13px; }
  .scraper-last-run { font-size: 10px; }

  .interval-dropdown { right: auto; left: 0; min-width: 180px; }

  .scraper-rows { padding: 16px 0 0; }
  .scraper-rows :deep(.scraper-rows) { grid-template-columns: 1fr; }
}

.interval-dropdown-body {
  padding: 12px;
}
.interval-dd-label {
  display: block; font-size: 12px; font-weight: 500; margin-bottom: 4px;
  color: var(--color-text, #1e293b);
}
.interval-dd-input {
  width: 100%; padding: 6px 8px; border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px; font-size: 13px; font-family: monospace; text-align: right;
  box-sizing: border-box;
}
.interval-dd-input:focus { outline: none; border-color: var(--color-primary, #2563eb); }
.interval-dd-hint {
  font-size: 11px; color: var(--color-text-secondary, #64748b); margin-top: 4px;
}
.interval-dd-actions {
  display: flex; justify-content: flex-end; gap: 6px; margin-top: 10px;
}
/* Buttons come from the global button system (buttons.css) via BaseButton. */

/* rows */
.scraper-rows { padding: 24px 0 0; }

/* Status row */
.scraper-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.dot-running { background: #22c55e; animation: pulse 1.5s infinite; }
.dot-idle { background: #94a3b8; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.scraper-status-text { font-size: 14px; font-weight: 600; color: var(--color-text, #1e293b); }
.scraper-last-run { font-size: 11px; color: var(--color-text-secondary, #64748b); }

/* Issues box in the run footer */
.run-issues-box {
  width: 100%;
  max-height: 250px;
  overflow-y: auto;
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--color-border, #e2e8f0);
}
.run-issues-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #dc2626;
  margin-bottom: 4px;
}
.run-issue-row { display: flex; gap: 8px; font-size: 12px; padding: 2px 0; align-items: baseline; }
.run-issue-row .issue-severity { font-weight: 700; font-size: 10px; text-transform: uppercase; flex-shrink: 0; }
.run-issue-row.issue-error .issue-severity { color: #dc2626; }
.run-issue-row.issue-warning .issue-severity { color: #d97706; }
.run-issue-row .issue-source { font-family: monospace; color: var(--color-text-secondary, #64748b); flex-shrink: 0; }
.run-issue-row .issue-message { color: var(--color-text, #1e293b); word-break: break-word; }

/* Progress bar — flex item filling available space in .scraper-status-row */
.scraper-progress-track {
  flex: 1; min-width: 80px; height: 6px;
  background: var(--color-border, #e2e8f0); border-radius: 3px;
  overflow: hidden;
}
.scraper-progress-fill {
  height: 100%; background: linear-gradient(90deg, #22c55e, #16a34a);
  border-radius: 3px; transition: width 0.3s ease;
}

</style>