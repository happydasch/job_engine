<template>
  <div class="skills-view">
    <PageTitle title="Skills" :count="`${filteredAllGaps.length} skill${filteredAllGaps.length === 1 ? '' : 's'}`" />

    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <EmptyState v-else-if="!data" title="No skills data" message="Run scrapers first to populate job data and identify skill gaps">
      <template #icon>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
        </svg>
      </template>
    </EmptyState>
    <template v-else-if="data">
      <FilterPanel
        v-model="filters.searchQuery"
        placeholder="Filter all skills…"
        show-search-icon
        :show-reset="true"
        :has-active-filters="hasActiveFilters"
        :has-advanced-filters="hasAdvancedFilters"
        @reset="onReset"
      >
        <template #below>
          <FilterSortSelect
            v-model="filters.sortBy"
            :options="sortOptions"
            label="Sort by"
            :show-order="true"
            :order="filters.sortOrder"
            @toggle-order="toggleSortOrder"
          />
        </template>
        <template #advanced>
          <FilterToggleGroup
            v-model="filters.priority"
            :options="priorityOptions"
            label="Priority"
            :multi="true"
          />
          <FilterToggleGroup
            v-model="filters.inProfile"
            :options="inProfileOptions"
            label="Profile"
            :multi="true"
          />
        </template>
      </FilterPanel>

      <SkillsGrid :gaps="filteredAllGaps" :on-add="showAddPicker" :on-remove="removeSkill" />
    </template>

    <!-- Add Skill Category Picker Modal -->
    <BaseModal
      :visible="!!addSkillName"
      :title="`Add skill: ${addSkillName || ''}`"
      size="small"
      @close="cancelAdd"
    >
      <p class="picker-hint">Choose a category to add this skill to:</p>
      <div class="picker-categories">
        <button
          v-for="cat in profileCategories"
          :key="cat"
          class="picker-cat-btn"
          :class="{ selected: selectedCategory === cat }"
          @click="selectedCategory = cat"
        >
          {{ cat }}
        </button>
      </div>
      <div class="picker-new-row">
        <input
          v-model="newCategoryName"
          class="pf-input"
          type="text"
          placeholder="Or type a new category name…"
          aria-label="New category name"
          @keydown.enter.prevent="confirmAddWithNewCategory"
        />
      </div>
      <template #footer>
        <BaseButton variant="ghost" @click="cancelAdd">Cancel</BaseButton>
        <BaseButton
          variant="primary"
          :disabled="!selectedCategory && !newCategoryName.trim()"
          @click="confirmAdd"
        >
          {{ adding ? 'Adding…' : 'Add Skill' }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useFetch } from '../composables/useFetch'
import { useFilters } from '../composables/useFilters'
import { useRefreshOnScrapeComplete } from '../composables/useRefreshOnScrapeComplete'
import { showToast } from '../composables/useToast'
import EmptyState from '../components/common/EmptyState.vue'
import SkillsGrid from '../components/skills/SkillsGrid.vue'
import PageTitle from '../components/common/PageTitle.vue'
import FilterPanel from '../components/common/FilterPanel.vue'
import FilterToggleGroup from '../components/common/filters/FilterToggleGroup.vue'
import FilterSortSelect from '../components/common/filters/FilterSortSelect.vue'
import BaseButton from '../components/common/BaseButton.vue'
import BaseModal from '../components/common/BaseModal.vue'

const data = ref(null)
const { execute: fetchSkills } = useFetch('')
const loading = ref(true)
const error = ref(null)

// Profile data for add/remove operations
const profile = ref(null)
const profileLoading = ref(false)
const profileError = ref(null)

// Add skill picker state
const addSkillName = ref(null)
const selectedCategory = ref('')
const newCategoryName = ref('')
const adding = ref(false)

const { filters, hasActiveFilters, reset } = useFilters({
  searchQuery: '',
  priority: new Set(),
  inProfile: new Set(),
  sortBy: 'frequency',
  sortOrder: 'desc',
}, 'job_engine_skills_filters')

const priorityOptions = [
  { value: 'Critical', label: 'Critical' },
  { value: 'High', label: 'High' },
  { value: 'Medium', label: 'Medium' },
  { value: 'Low', label: 'Low' },
]

const inProfileOptions = [
  { value: 'true', label: 'In Profile' },
  { value: 'false', label: 'Not in Profile' },
]

const sortOptions = [
  { value: 'frequency', label: 'Frequency' },
  { value: 'skill', label: 'Name' },
  { value: 'priority', label: 'Priority' },
  { value: 'avg_match_score', label: 'Match Score' },
]

function toggleSortOrder() {
  filters.sortOrder = filters.sortOrder === 'asc' ? 'desc' : 'asc'
}

function onReset() {
  reset()
}

const filteredAllGaps = computed(() => {
  if (!data.value?.all_gaps) return []
  const q = filters.searchQuery.toLowerCase().trim()
  const priSet = filters.priority
  const inProfSet = filters.inProfile
  const sortBy = filters.sortBy
  const order = filters.sortOrder
  const list = data.value.all_gaps.filter(g => {
    if (q && !g.skill.toLowerCase().includes(q)) return false
    if (priSet.size > 0 && !priSet.has(g.priority)) return false
    if (inProfSet.size > 0 && !inProfSet.has(String(g.in_profile))) return false
    return true
  })
  // Sort
  const sorted = [...list]
  sorted.sort((a, b) => {
    let cmp = 0
    if (sortBy === 'skill') {
      cmp = a.skill.localeCompare(b.skill)
    } else if (sortBy === 'priority') {
      const prioOrder = { Critical: 0, High: 1, Medium: 2, Low: 3 }
      cmp = (prioOrder[a.priority] ?? 4) - (prioOrder[b.priority] ?? 4)
    } else if (sortBy === 'avg_match_score') {
      cmp = a.avg_match_score - b.avg_match_score
    } else { // frequency (default)
      cmp = a.frequency - b.frequency
    }
    return order === 'asc' ? cmp : -cmp
  })
  return sorted
})

// Profile categories (computed from loaded profile)
const profileCategories = computed(() => {
  const s = profile.value?.skills
  if (!s || typeof s !== 'object') return []
  return Object.keys(s)
})

async function loadProfile() {
  profileLoading.value = true
  profileError.value = null
  try {
    const res = await fetch('/api/profile/data')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    profile.value = await res.json()
  } catch (e) {
    // Never fabricate an empty profile — a later PATCH could clobber the real one
    console.error('Failed to load profile:', e)
    profileError.value = e.message || 'Failed to load profile'
    showToast(`Profile unavailable — adding skills is disabled: ${profileError.value}`, 'error')
    profile.value = null
  } finally {
    profileLoading.value = false
  }
}

// Add skill handlers
function showAddPicker(skillName) {
  if (!profile.value) return
  addSkillName.value = skillName
  selectedCategory.value = ''
  newCategoryName.value = ''
}

function cancelAdd() {
  addSkillName.value = null
  selectedCategory.value = ''
  newCategoryName.value = ''
  adding.value = false
}

function confirmAddWithNewCategory() {
  const name = newCategoryName.value.trim()
  if (name) {
    selectedCategory.value = name
    confirmAdd()
  }
}

async function confirmAdd() {
  const skill = addSkillName.value
  let category = selectedCategory.value
  if (!category || !category.trim()) {
    category = newCategoryName.value.trim()
  }
  if (!category) return

  adding.value = true
  try {
    const updatedSkills = { ...(profile.value?.skills || {}) }
    if (!updatedSkills[category]) {
      updatedSkills[category] = []
    }
    if (!updatedSkills[category].includes(skill)) {
      updatedSkills[category] = [...updatedSkills[category], skill]
    }

    const res = await fetch('/api/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section: 'skills', values: updatedSkills }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(body || `HTTP ${res.status}`)
    }

    showToast(`Added "${skill}" to ${category}`, 'success')
    cancelAdd()
    await loadProfile()
    await refreshSkills()
  } catch (e) {
    showToast(`Failed to add skill: ${e.message}`, 'error')
  } finally {
    adding.value = false
  }
}

// Remove skill handler
async function removeSkill(skillName) {
  const s = profile.value?.skills
  if (!s || typeof s !== 'object') return

  // Find which category the skill is in
  let foundCategory = null
  for (const [cat, skills] of Object.entries(s)) {
    if (Array.isArray(skills) && skills.includes(skillName)) {
      foundCategory = cat
      break
    }
  }
  if (!foundCategory) {
    showToast(`Skill "${skillName}" not found in profile`, 'error')
    return
  }

  try {
    const updatedSkills = { ...s }
    updatedSkills[foundCategory] = updatedSkills[foundCategory].filter(
      sk => sk !== skillName
    )
    // Remove empty categories
    if (updatedSkills[foundCategory].length === 0) {
      delete updatedSkills[foundCategory]
    }

    const res = await fetch('/api/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section: 'skills', values: updatedSkills }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(body || `HTTP ${res.status}`)
    }

    showToast(`Removed "${skillName}" from profile`, 'success')
    await loadProfile()
    await refreshSkills()
  } catch (e) {
    showToast(`Failed to remove skill: ${e.message}`, 'error')
  }
}

async function refreshSkills() {
  try {
    const result = await fetchSkills('/api/skills')
    data.value = result
  } catch (e) {
    // Keep existing data
  }
}

onMounted(async () => {
  try {
    const result = await fetchSkills('/api/skills')
    data.value = result
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
  await loadProfile()
})

// Re-fetch skills data when a scrape run adds/removes jobs
useRefreshOnScrapeComplete(() => refreshSkills())
</script>

<style scoped>
.loading, .error { padding: 2rem; text-align: center; }

/* Category Picker Modal (BaseModal handles shell/backdrop/Escape) */
.picker-hint { font-size: 0.8125rem; color: var(--color-text-secondary, #64748b); margin: 0 0 0.75rem; }
.picker-categories {
  display: flex; flex-wrap: wrap; gap: 0.375rem;
  margin-bottom: 0.75rem;
}
.picker-cat-btn {
  padding: 0.375rem 0.75rem; border-radius: 6px; font-size: 0.75rem;
  font-weight: 500; cursor: pointer; border: 1px solid var(--color-border, #e2e8f0);
  background: var(--color-bg-card, #fff); color: var(--color-text, #1e293b);
  transition: all 0.12s;
}
.picker-cat-btn:hover { border-color: #3b82f6; color: #3b82f6; }
.picker-cat-btn.selected { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.picker-new-row { margin-top: 0.5rem; }
.picker-new-row .pf-input {
  width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px; font-size: 0.8125rem; outline: none; box-sizing: border-box;
}
.picker-new-row .pf-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,0.15); }
</style>