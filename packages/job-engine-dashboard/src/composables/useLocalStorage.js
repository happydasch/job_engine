/**
 * useLocalStorage — reactive localStorage-backed ref with Set serialization.
 *
 * Creates a `ref` that initialises from `localStorage` (JSON.parse) and
 * auto-persists every change via `watch({ deep: true })`.
 *
 * Set instances are serialized as `{ __type: 'Set', values: [...] }` and
 * reconstructed on load.
 *
 * @param {string} key        localStorage key
 * @param {*}      defaultValue  fallback when nothing is stored
 * @returns {import('vue').Ref}
 */
import { ref, watch } from 'vue'

function serialize(value) {
  if (value instanceof Set) {
    return { __type: 'Set', values: [...value] }
  }
  return value
}

function deserialize(value) {
  if (value && typeof value === 'object' && value.__type === 'Set') {
    return new Set(value.values)
  }
  return value
}

export function useLocalStorage(key, defaultValue) {
  let initial = defaultValue

  try {
    const raw = localStorage.getItem(key)
    if (raw !== null) {
      const parsed = JSON.parse(raw)
      initial = deserialize(parsed)
    }
  } catch (e) {
    // localStorage unavailable, corrupted, or quota exceeded — use default
    console.warn(`useLocalStorage: could not restore "${key}" from localStorage:`, e)
  }

  const data = ref(initial)

  // Deep watch: persist on every change
  watch(
    data,
    (val) => {
      try {
        const serialized = JSON.stringify(serialize(val), (_, v) =>
          v instanceof Set ? { __type: 'Set', values: [...v] } : v
        )
        localStorage.setItem(key, serialized)
      } catch (e) {
        // localStorage full or unavailable — degrade, state stays in-memory
        console.warn(`useLocalStorage: could not persist "${key}" to localStorage:`, e)
      }
    },
    { deep: true }
  )

  return data
}