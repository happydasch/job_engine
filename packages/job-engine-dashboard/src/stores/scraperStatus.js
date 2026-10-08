import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { showToast } from '../composables/useToast'

/**
 * Scraper run status/history — singleton, shared across ScraperPanel (sidebar),
 * ScrapersView (full page) and ScraperList (pills).
 *
 * Previously each of those components polled /api/scrape/status independently
 * with its own local refs, so a run triggered from one component (e.g. the
 * sidebar) never updated the others (e.g. the pills' last_run_at) until they
 * happened to remount. A single shared poll loop here means every consumer
 * sees the same state, and a background/cron-triggered run (which no
 * component "triggers" at all) still gets picked up within one heartbeat.
 */
export const useScraperStatusStore = defineStore('scraperStatus', () => {
  const status = ref(null)
  const scrapers = ref([])
  const history = ref([])
  const scrapersLoading = ref(false)
  const progress = ref(0)
  const lastError = ref(null) // last background-load error message (null when healthy)
  const lastRunCompletedAt = ref(0) // timestamp when a run transitioned running→completed

  let pollTimer = null
  let initialized = false
  let consecutiveFailures = 0 // background poll failures; toast after a streak

  const isRunning = computed(() => status.value?.status === 'running' || status.value?.running === true)
  const scraperBadges = computed(() => {
    const ps = status.value?.scraper_statuses || {}
    return Object.entries(ps).map(([scraper, s]) => ({ scraper, status: s }))
  })

  function noteFailure(context, e) {
    const msg = e?.message || String(e)
    lastError.value = `${context}: ${msg}`
    console.error(`[scraperStatus] ${context} failed:`, e)
    consecutiveFailures++
    // Don't spam: only toast once per failure streak of the background poller
    if (consecutiveFailures === 3) {
      showToast(`Scraper status unavailable (${msg})`, 'error')
    }
  }

  function noteSuccess() {
    consecutiveFailures = 0
    lastError.value = null
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/api/scrape/status')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const wasRunning = isRunning.value
      status.value = data
      noteSuccess()

      const total = data.scrapers_total ?? 1
      const done = data.scrapers_completed ?? 0
      progress.value = Math.round((done / total) * 100)

      if (wasRunning && !isRunning.value) {
        // Run just finished (however/wherever it was started) — refresh the
        // list + history so last_run_at and totals catch up everywhere.
        loadScrapers()
        loadHistory()
        lastRunCompletedAt.value = Date.now()
      }
    } catch (e) {
      // Next poll tick retries; surfaced via lastError/toast.
      noteFailure('Fetch scrape status', e)
    }
  }

  async function loadScrapers() {
    scrapersLoading.value = true
    try {
      const res = await fetch('/api/scrape/scrapers')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      scrapers.value = data.scrapers
    } catch (e) {
      noteFailure('Load scrapers', e)
    }
    scrapersLoading.value = false
  }

  async function loadHistory() {
    try {
      const res = await fetch('/api/scrape/history')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      history.value = await res.json()
    } catch (e) {
      noteFailure('Load scrape history', e)
    }
  }

  // Poll fast while a run is active, slow (heartbeat) while idle — the slow
  // tick is what catches runs started outside the UI entirely (auto-run
  // schedule/cron) so the dashboard doesn't require a page reload to see them.
  function schedulePoll() {
    clearTimeout(pollTimer)
    pollTimer = setTimeout(async () => {
      await fetchStatus()
      schedulePoll()
    }, isRunning.value ? 2000 : 15000)
  }

  function ensurePolling() {
    if (pollTimer) return
    schedulePoll()
  }

  async function triggerRun(scraper = null) {
    const body = scraper ? { scraper } : {}
    const url = scraper ? `/api/scrape/scraper/${scraper}` : '/api/scrape'
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      // Re-check status right away (don't wait for the heartbeat) even on
      // a 409 (already running) so the UI picks up the active state.
      await fetchStatus()
      ensurePolling()
      if (res.ok) return { success: true }
      const err = await res.json().catch(() => ({}))
      return { success: false, error: err.error || err.detail || `HTTP ${res.status}` }
    } catch (e) {
      return { success: false, error: e.message }
    }
  }

  async function cancelRun() {
    if (!status.value?.task_id) return { success: false, error: 'No active run to cancel' }
    let result = { success: true }
    try {
      const res = await fetch(`/api/scrape/cancel/${status.value.task_id}`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        result = { success: false, error: err.error || err.detail || `HTTP ${res.status}` }
      }
    } catch (e) {
      result = { success: false, error: e.message }
    }
    await fetchStatus()
    return result
  }

  async function init() {
    if (initialized) return
    initialized = true
    await Promise.all([fetchStatus(), loadScrapers(), loadHistory()])
    ensurePolling()
  }

  /**
   * Stop the polling loop and reset initialization state.
   * Call from onUnmounted in any component that starts polling,
   * so the loop doesn't persist forever as a singleton.
   */
  function destroy() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
    initialized = false
  }

  return {
    status,
    scrapers,
    history,
    scrapersLoading,
    progress,
    lastError,
    isRunning,
    scraperBadges,
    lastRunCompletedAt,
    init,
    fetchStatus,
    loadScrapers,
    loadHistory,
    triggerRun,
    cancelRun,
    destroy,
  }
})
