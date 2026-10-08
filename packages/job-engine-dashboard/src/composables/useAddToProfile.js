import { ref } from 'vue'
import { apiFetch } from './apiFetch'
import { showToast } from './useToast'

/**
 * useAddToProfile — shared "add item to profile" logic.
 *
 * Deduplicates the profile-load + exists-check + append-items flow that was
 * copy-pasted between JobDetailView (skill popover) and AiAnalysisPane
 * (pill popover).
 *
 * Returns:
 * - profileData          raw profile object (ref)
 * - skillCategories      skill sub-category names (ref, defaults to ['extracted'])
 * - loadProfileData()    fetch /api/profile/data
 * - existsInProfile(item, section, subKey?)
 * - addToProfile(section, item, subKey?) — POSTs append-items, toasts, refreshes
 */
export function useAddToProfile() {
  const profileData = ref(null)
  const skillCategories = ref(['extracted'])

  async function loadProfileData() {
    try {
      const data = await apiFetch('/api/profile/data')
      profileData.value = data
      const cats = Object.keys(data.skills || {})
      if (cats.length) {
        skillCategories.value = cats
      }
    } catch (e) {
      // Popover still works with the default category list
      console.error('Failed to load profile data:', e)
    }
  }

  function existsInProfile(item, section, subKey) {
    const data = profileData.value
    if (!data) return false
    if (subKey) {
      // Dict-type section (skills with categories)
      const list = data[section]?.[subKey]
      if (Array.isArray(list)) {
        return list.some(s => String(s).toLowerCase() === item.toLowerCase())
      }
      return false
    }
    // Flat array section (career_goals, behavioral_keywords)
    const list = data[section]
    return Array.isArray(list) && list.some(s => String(s).toLowerCase() === item.toLowerCase())
  }

  async function addToProfile(section, item, subKey = null) {
    try {
      const body = { section, items: [item] }
      if (subKey) body.sub_key = subKey
      await apiFetch('/api/profile/append-items', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      // Refresh profile data so exist-check updates
      await loadProfileData()
      showToast(`Added "${item}" to profile ${section}${subKey ? ' / ' + subKey : ''}`)
    } catch (e) {
      showToast(e.message || 'Failed to add to profile', 'error')
    }
  }

  return { profileData, skillCategories, loadProfileData, existsInProfile, addToProfile }
}
