/**
 * useRecentlyViewed — tracks jobs the user has viewed, persisted in localStorage.
 *
 * Stores a list of job summaries (max 10) sorted most-recently-viewed first.
 * Each entry is compact enough for JobListItem usage on the dashboard.
 */
import { ref } from 'vue'

const STORAGE_KEY = 'job_engine_recently_viewed'
const MAX_ITEMS = 10

const recentlyViewed = ref([])

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    recentlyViewed.value = raw ? JSON.parse(raw) : []
  } catch { recentlyViewed.value = [] /* localStorage unavailable or corrupted */ }
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(recentlyViewed.value))
  } catch { /* localStorage full or unavailable — silently degrade */
  }
}

// Initialize on first import
load()

/**
 * Record a job as recently viewed. Moves existing entries to the top;
 * caps the list at MAX_ITEMS.
 */
export function recordJobView(job) {
  if (!job || !job.external_id) return

  // Build the minimal job summary needed by JobListItem
  const entry = {
    external_id: job.external_id,
    title: job.title || 'Untitled',
    company: job.company || null,
    platform: job.platform || null,
    match_score: job.match_score || 0,
    remote: !!job.remote,
    location: job.location || null,
    url: job.url || null,
    viewed_at: new Date().toISOString(),
  }

  // Remove any existing entry for the same job (deduplicate)
  const filtered = recentlyViewed.value.filter(
    (e) => e.external_id !== entry.external_id
  )

  // Prepend the new entry (most recent first)
  recentlyViewed.value = [entry, ...filtered].slice(0, MAX_ITEMS)
  save()
}

/**
 * Reactive list of recently viewed job summaries.
 * Most recent first, length ≤ MAX_ITEMS.
 */
export function useRecentlyViewed() {
  return recentlyViewed
}