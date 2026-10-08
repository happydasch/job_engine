import { reactive, computed, watch } from 'vue'

/**
 * Jobs filter state composable with localStorage persistence.
 *
 * Uses snake_case property names intentionally — they mirror the URL query params
 * sent to the backend API (e.g. `sort_by`, `min_score`), so that toQueryParams()
 * can build the API request directly without mapping between naming conventions.
 *
 * @param {string} [storageKey] — Optional localStorage key for persistence.
 */
export function useJobFilters(storageKey = null) {
  // Build initial state: localStorage first, then defaults for missing keys
  let saved
  if (storageKey) {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) saved = JSON.parse(raw)
    } catch { /* localStorage unavailable or corrupted — use defaults */
    }
  }

  const defaults = {
    q: '',
    sort_by: 'match_score',
    sort_order: 'desc',
    min_score: 0,
    platform: '',
    remote: '',
    skill: '',
    location: '',
    experience_level: '',
    category: '',
    contract_type: '',
    show_hidden: false,
    show_favorites: false,
    show_applied: false,
    show_enriched: false,
    hidden_only: false,
    page: 1,
    per_page: 50,
  }

  const initial = saved ? { ...defaults, ...saved } : { ...defaults }

  const filters = reactive(initial)

  const hasActiveFilters = computed(() => {
    const f = filters
    return !!(f.q || f.min_score > 0 || f.platform || f.remote || f.skill || f.location || f.experience_level || f.category || f.contract_type || f.show_hidden || f.hidden_only || f.show_favorites || f.show_applied || f.show_enriched)
  })

  // Auto-persist to localStorage when storageKey is provided
  if (storageKey) {
    watch(
      filters,
      (val) => {
        try {
          localStorage.setItem(storageKey, JSON.stringify(val))
        } catch { /* localStorage full or unavailable — silently degrade */ }
      },
      { deep: true }
    )
  }

  function resetFilters() {
    Object.assign(filters, {
      q: '',
      sort_by: 'match_score',
      sort_order: 'desc',
      min_score: 0,
      platform: '',
      remote: '',
      skill: '',
      location: '',
      experience_level: '',
      category: '',
      contract_type: '',
      show_hidden: false,
      show_favorites: false,
      show_applied: false,
      show_enriched: false,
      hidden_only: false,
      page: 1,
      per_page: 50,
    })
    if (storageKey) {
      try {
        localStorage.removeItem(storageKey)
      } catch { /* Silently degrade */ }
    }
  }

  function toQueryParams() {
    const f = filters
    const params = new URLSearchParams()
    if (f.q) params.set('q', f.q)
    if (f.sort_by !== 'match_score') params.set('sort_by', f.sort_by)
    if (f.sort_order !== 'desc') params.set('sort_order', f.sort_order)
    if (f.min_score > 0) params.set('min_score', String(f.min_score))
    if (f.platform) params.set('platform', f.platform)
    if (f.remote) params.set('remote', f.remote)
    if (f.skill) params.set('skill', f.skill)
    if (f.location) params.set('location', f.location)
    if (f.experience_level) params.set('experience_level', f.experience_level)
    if (f.category) params.set('category', f.category)
    if (f.contract_type) params.set('contract_type', f.contract_type)
    if (f.show_hidden) params.set('show_hidden', 'true')
    if (f.hidden_only) params.set('hidden_only', 'true')
    if (f.show_favorites) params.set('show_favorites', 'true')
    if (f.show_applied) params.set('show_applied', 'true')
    if (f.show_enriched) params.set('show_enriched', 'true')
    if (f.page > 1) params.set('page', String(f.page))
    if (f.per_page !== 50) params.set('per_page', String(f.per_page))
    return params.toString()
  }

  return { filters, hasActiveFilters, resetFilters, toQueryParams }
}