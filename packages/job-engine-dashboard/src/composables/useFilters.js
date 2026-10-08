import { reactive, computed, watch } from 'vue'

/**
 * Deep-clone a plain value (pojo, array, Set, primitives).
 */
function clone(val) {
  if (val instanceof Set) return new Set(val)
  return JSON.parse(JSON.stringify(val))
}

/**
 * Standardised filter state composable.
 *
 * Provides a single reactive `filters` object, a `hasActiveFilters` check
 * that compares each dimension against its default, and a `reset()` function.
 *
 * When `storageKey` is provided, filter state is auto-persisted to localStorage
 * and restored on creation. `reset()` also clears the stored entry.
 *
 * @example
 * ```js
 * const { filters, hasActiveFilters, reset } = useFilters({
 *   search: '',
 *   sortBy: 'name',
 *   sortOrder: 'asc',
 * })
 * // filters.search, filters.sortBy — reactive
 * // hasActiveFilters — computed: true when any filter differs from default
 * // reset() — restores all values to defaults
 * ```
 *
 * @param {Object} defaults — Initial/default values for all filter dimensions.
 * @param {string} [storageKey] — Optional localStorage key for persistence.
 * @returns {{ filters, hasActiveFilters, reset }}
 */
export function useFilters(defaults = {}, storageKey = null) {
  let initial = { ...defaults }

  // Restore persisted state when storageKey is provided
  if (storageKey) {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw !== null) {
        const saved = JSON.parse(raw)
        // Merge so that missing keys fall back to defaults
        initial = { ...initial, ...saved }
        // Restore Set values
        for (const [k, v] of Object.entries(initial)) {
          if (v && typeof v === 'object' && v.__type === 'Set') {
            initial[k] = new Set(v.values)
          }
        }
      }
    } catch (e) {
      // localStorage unavailable or corrupted — use defaults
      console.warn(`useFilters: could not restore "${storageKey}" from localStorage:`, e)
    }
  }

  const filters = reactive(clone(initial))

  const hasActiveFilters = computed(() => {
    return Object.keys(defaults).some(key => {
      const val = filters[key]
      const def = defaults[key]
      if (val instanceof Set) return val.size > 0
      if (typeof val === 'boolean') return val !== def
      if (typeof val === 'number') return val !== def
      return val !== def
    })
  })

  // Auto-persist when storageKey is provided
  if (storageKey) {
    watch(
      filters,
      (val) => {
        try {
          const serialized = JSON.stringify(val, (_, v) =>
            v instanceof Set ? { __type: 'Set', values: [...v] } : v
          )
          localStorage.setItem(storageKey, serialized)
        } catch (e) {
          // localStorage full or unavailable — degrade, state stays in-memory
          console.warn(`useFilters: could not persist "${storageKey}" to localStorage:`, e)
        }
      },
      { deep: true }
    )
  }

  function reset() {
    Object.assign(filters, clone(defaults))
    if (storageKey) {
      try {
        localStorage.removeItem(storageKey)
      } catch (e) {
        // localStorage unavailable
        console.warn(`useFilters: could not clear "${storageKey}" from localStorage:`, e)
      }
    }
  }

  return { filters, hasActiveFilters, reset }
}