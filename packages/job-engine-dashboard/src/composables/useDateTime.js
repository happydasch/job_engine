/**
 * Shared date/time formatting composable.
 *
 * All table and list views use this so datetime display is consistent
 * across the SPA.  Format: DD/MM/YYYY, HH:mm:ss (24h, zero-padded).
 *
 * Usage:
 *   const { formatDateTime, formatDate, timeAgo, formatDuration } = useDateTime()
 *   formatDateTime(row.started_at)  // → "17/07/2026, 22:08:35"
 */
export function useDateTime() {
  /**
   * Parse an ISO string that may lack timezone info (naive DB ISO).
   * Treats naive strings as UTC by appending 'Z'.
   */
  function parseUTC(dateStr) {
    if (!dateStr) return null
    const hasTz = /[Zz]$/.test(dateStr) || /[+-]\d{2}:?\d{2}$/.test(dateStr)
    return new Date(hasTz ? dateStr : dateStr + 'Z')
  }

  /**
   * Full datetime — DD/MM/YYYY, HH:mm:ss
   * Primary format for table cells.
   */
  function formatDateTime(iso) {
    if (!iso) return '—'
    try {
      const d = parseUTC(iso)
      const day = String(d.getDate()).padStart(2, '0')
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const year = d.getFullYear()
      const hours = String(d.getHours()).padStart(2, '0')
      const minutes = String(d.getMinutes()).padStart(2, '0')
      const seconds = String(d.getSeconds()).padStart(2, '0')
      return `${day}/${month}/${year}, ${hours}:${minutes}:${seconds}`
    } catch { return iso /* Date parsing failed — return raw string as fallback */ }
  }

  /**
   * Date only — DD/MM/YYYY.
   * Compact format for hero tags, list items, etc.
   */
  function formatDate(iso) {
    if (!iso) return '—'
    try {
      const d = parseUTC(iso)
      const day = String(d.getDate()).padStart(2, '0')
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const year = d.getFullYear()
      return `${day}/${month}/${year}`
    } catch { return iso /* Date parsing failed — return raw string as fallback */ }
  }

  /**
   * Relative time for recent items, falls back to DD/MM/YYYY for older dates.
   * Used in scrape run lists, sidebar panels, etc.
   */
  function timeAgo(iso) {
    if (!iso) return ''
    try {
      const d = parseUTC(iso)
      const now = new Date()
      const diffMin = Math.floor((now - d) / 60000)
      if (diffMin < 1) return 'just now'
      if (diffMin < 60) return `${diffMin}m ago`
      const diffHr = Math.floor(diffMin / 60)
      if (diffHr < 24) return `${diffHr}h ago`
      const diffDay = Math.floor(diffHr / 24)
      if (diffDay < 30) return `${diffDay}d ago`
      return formatDate(iso)
    } catch { return iso /* Date parsing failed — return raw string as fallback */ }
  }

  /**
   * Human-readable duration between two ISO timestamps.
   */
  function formatDuration(start, end) {
    if (!start || !end) return '—'
    try {
      const ms = parseUTC(end) - parseUTC(start)
      const s = Math.round(ms / 1000)
      if (s < 60) return `${s}s`
      return `${Math.floor(s / 60)}m ${s % 60}s`
    } catch { return '—' /* Date parsing failed — return fallback */ }
  }

  /**
   * Format a duration in seconds (e.g. from API field).
   */
  function formatSeconds(seconds) {
    if (seconds == null) return '—'
    if (seconds < 60) return `${Math.round(seconds)}s`
    const min = Math.floor(seconds / 60)
    const sec = Math.round(seconds % 60)
    return `${min}m ${sec}s`
  }

  return { parseUTC, formatDateTime, formatDate, timeAgo, formatDuration, formatSeconds }
}