import { apiFetch } from './apiFetch'
import { showToast } from './useToast'

/**
 * useJobActions — shared job favorite/hide toggles with consistent toasts.
 *
 * Replaces the triplicated fetch+toast logic previously copy-pasted across
 * JobsView, CompanyDetailView and JobDetailView.
 *
 * Errors are surfaced via toast (not rethrown); on failure the promise
 * resolves to `undefined` so callers can skip success-only follow-ups.
 *
 * @param {(id: string) => object|null|undefined} findJob
 *   Returns the reactive job object to mutate (must have external_id,
 *   favorite, hidden), or null/undefined when not found.
 *
 * @example
 * const { toggleFav, toggleHide } = useJobActions(
 *   (id) => jobs.value.find(j => j.external_id === id)
 * )
 */
export function useJobActions(findJob) {
  async function toggleFav(id) {
    try {
      const data = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/toggle-fav`, { method: 'PATCH' })
      const job = findJob(id)
      if (job) job.favorite = data.favorite
      showToast(data.favorite ? 'Added to favorites' : 'Removed from favorites')
      return data.favorite
    } catch (e) {
      showToast(`Failed to toggle favorite: ${e.message}`, 'error')
    }
  }

  async function toggleHide(id) {
    try {
      const data = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/toggle-hide`, { method: 'PATCH' })
      const job = findJob(id)
      if (job) job.hidden = data.hidden
      showToast(data.hidden ? 'Job hidden' : 'Job unhidden')
      return data.hidden
    } catch (e) {
      showToast(`Failed to toggle hide: ${e.message}`, 'error')
    }
  }

  return { toggleFav, toggleHide }
}
