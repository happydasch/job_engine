/**
 * apiFetch — minimal fetch helper for one-off API calls outside useFetch.
 *
 * Parses the JSON response and throws Error(detail || HTTP status) on
 * non-OK responses, so callers never have to remember to check res.ok.
 * Sends/receives JSON by default when a body is provided.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<any>} parsed JSON body
 */
export async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Accept': 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.error || `HTTP ${res.status}`)
  }
  return res.json()
}
