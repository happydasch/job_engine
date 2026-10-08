<template>
  <div class="jobs-page">
    <PageTitle title="Job Matches" :count="`${total} job${total === 1 ? '' : 's'}`" />

    <JobFilters :filters="filters" :platforms="platforms" :skills="skills" :locations="locations" :experience-levels="experienceLevels" :categories="categories" :contract-types="contractTypes" :has-active-filters="hasActiveFilters" @update="onFilterChange" />

    <EmptyState v-if="loading" loading message="Loading jobs..." />
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>

      <Card flush class="job-listing-list" v-if="jobs.length">
        <JobCard
          v-for="job in jobs"
          :key="job.external_id"
          :job="job"
          @toggle-fav="onToggleFav"
          @toggle-hide="onToggleHide"
          @apply="onApply"
          @transition="onTransition"
          @reopen="onReopen"
          @delete="onDeleteApp"
        />
      </Card>

      <EmptyState v-else :title="hasFilters ? 'No jobs match these filters' : 'No jobs yet'" :message="hasFilters ? 'Try different keywords or adjust filters' : 'Run scrapers first to populate jobs'">
          <template #icon>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
              <path d="M8 11h6"/><path d="M11 8v6"/>
            </svg>
          </template>
        </EmptyState>

      <JobPagination
        v-if="total > perPage"
        :page="page"
        :total="total"
        :per-page="perPage"
        @page-change="goToPage"
      />
    </div>
  <!-- Confirm Delete Application Modal -->
    <ConfirmModal
      :visible="showDeleteConfirm"
      title="Delete Application"
      message="Delete this application permanently? This cannot be undone."
      confirm-text="Delete"
      confirm-variant="danger"
      @confirm="confirmDeleteApp"
      @cancel="cancelDeleteApp"
    />
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { ref, onMounted, watch } from 'vue'
import { useFetch } from '../composables/useFetch'
import { useJobFilters } from '../composables/useJobFilters'
import { useApplicationStatus } from '../composables/useApplicationStatus'
import { useRefreshOnScrapeComplete } from '../composables/useRefreshOnScrapeComplete'
import { showToast } from '../composables/useToast'
import { useJobActions } from '../composables/useJobActions'
import JobFilters from '../components/jobs/JobFilters.vue'
import JobCard from '../components/jobs/JobCard.vue'
import JobPagination from '../components/jobs/JobPagination.vue'
import ConfirmModal from '../components/common/ConfirmModal.vue'
import PageTitle from '../components/common/PageTitle.vue'
import Card from '../components/common/Card.vue'
import EmptyState from '../components/common/EmptyState.vue'

const { filters, hasActiveFilters, toQueryParams } = useJobFilters('job_engine_jobs_filters')
const { execute: fetchJobsApi } = useFetch('')
const { createApplication, transitionApp, reopenApp, deleteApp } = useApplicationStatus()
const { toggleFav, toggleHide } = useJobActions((id) => jobs.value.find(j => j.external_id === id))

const jobs = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(50)
const loading = ref(false)
const error = ref(null)
const platforms = ref([])
const skills = ref([])
const locations = ref([])
const experienceLevels = ref([])
const categories = ref([])
const contractTypes = ref([])

// Confirm delete modal state
const showDeleteConfirm = ref(false)
const pendingDeleteAppId = ref(null)

const hasFilters = hasActiveFilters
const route = useRoute()

// ── URL query param sync ──
const routeParamMap = {
  q: 'q', platform: 'platform', remote: 'remote',
  skill: 'skill', location: 'location',
  experience_level: 'experience_level', category: 'category',
  contract_type: 'contract_type',
  sort_by: 'sort_by', sort_order: 'sort_order',
  min_score: 'min_score',
  show_hidden: 'show_hidden', hidden_only: 'hidden_only',
  show_favorites: 'show_favorites', show_applied: 'show_applied',
  show_enriched: 'show_enriched',
}

// Query params that map to boolean filter state — coerced rather than kept as strings.
const booleanParams = new Set([
  'show_hidden', 'hidden_only', 'show_favorites', 'show_applied', 'show_enriched',
])

function applyRouteQuery() {
  const query = route.query
  let changed = false
  for (const [routeKey, filterKey] of Object.entries(routeParamMap)) {
    if (query[routeKey] === undefined || query[routeKey] === null) continue
    const raw = String(query[routeKey]).trim()
    if (!raw) continue
    let val
    if (booleanParams.has(routeKey)) val = raw === 'true'
    else if (routeKey === 'min_score') {
      val = Number(raw)
      if (Number.isNaN(val)) continue
    } else val = raw
    if (val !== filters[filterKey]) {
      filters[filterKey] = val
      changed = true
    }
  }
  if (query.page !== undefined) {
    const p = parseInt(query.page)
    if (!isNaN(p) && p > 0 && p !== filters.page) {
      filters.page = p
      changed = true
    }
  }
  return changed
}

async function fetchJobs() {
  loading.value = true; error.value = null
  try {
    const params = toQueryParams()
    const result = await fetchJobsApi(`/api/jobs?${params}`)
    if (result) {
      jobs.value = result.jobs || []
      total.value = result.total || 0
      page.value = result.page || 1
      perPage.value = result.per_page || 50
      if (result.filters) {
        platforms.value = result.filters.platforms || []
        skills.value = result.filters.skills || []
        locations.value = result.filters.locations || []
        experienceLevels.value = result.filters.experience_levels || []
        categories.value = result.filters.categories || []
        contractTypes.value = result.filters.contract_types || []
      }
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onFilterChange(newFilters) {
  if (newFilters) {
    // Pass filter values as-is — backend handles case-insensitive matching
    const filtersChanged = Object.keys(newFilters).some(
      (k) => k !== 'page' && newFilters[k] !== filters[k]
    )
    Object.assign(filters, newFilters)
    // A changed filter narrows/widens the result set, so an old page number can
    // land past the end of a shorter list and render empty — always go to page 1.
    if (filtersChanged) filters.page = 1
  }
  fetchJobs()
}

function goToPage(p) {
  filters.page = p
  onFilterChange()
}

async function onToggleFav(id) {
  await toggleFav(id)
  // Favorites-only list must gain/drop the row immediately, not after the cache TTL.
  if (filters.show_favorites) await fetchJobs()
}

async function onToggleHide(id) {
  const hidden = await toggleHide(id)
  if (filters.hidden_only) {
    await fetchJobs()
    return
  }
  // Keep in list when "show hidden" filter is active (dimmed via CSS),
  // otherwise fade out then remove
  if (hidden && !filters.show_hidden) {
    setTimeout(() => {
      const idx = jobs.value.findIndex(j => j.external_id === id)
      if (idx !== -1) jobs.value.splice(idx, 1)
    }, 300)
  }
}

async function onApply(jobId) {
  try {
    const result = await createApplication(jobId)
    const job = jobs.value.find(j => j.external_id === jobId)
    if (job) {
      job.application_id = result.application_id
      job.application_status = 'applied'
    }
    showToast('Application recorded')
  } catch (e) {
    showToast(e.message || 'Failed to apply', 'error')
  }
}

async function onTransition({ appId, newStatus }) {
  try {
    await transitionApp(appId, newStatus)
    await fetchJobs()
    showToast(`Status updated to ${newStatus}`)
  } catch (e) {
    showToast(e.message || 'Failed to update status', 'error')
  }
}

async function onReopen(appId) {
  try {
    await reopenApp(appId)
    await fetchJobs()
    showToast('Application reopened')
  } catch (e) {
    showToast(e.message || 'Failed to reopen', 'error')
  }
}

async function onDeleteApp(appId) {
  pendingDeleteAppId.value = appId
  showDeleteConfirm.value = true
}

async function confirmDeleteApp() {
  showDeleteConfirm.value = false
  const appId = pendingDeleteAppId.value
  pendingDeleteAppId.value = null
  if (!appId) return
  try {
    await deleteApp(appId)
    await fetchJobs()
    showToast('Application deleted')
  } catch (e) {
    showToast(e.message || 'Failed to delete', 'error')
  }
}

function cancelDeleteApp() {
  showDeleteConfirm.value = false
  pendingDeleteAppId.value = null
}

onMounted(() => {
  applyRouteQuery()
  fetchJobs()
})

// Watch route query changes (e.g. when user navigates from a skill link)
watch(() => route.query, () => {
  if (applyRouteQuery()) {
    fetchJobs()
  }
})

// Re-fetch current filtered list when a scrape run adds/removes jobs
useRefreshOnScrapeComplete(() => fetchJobs())
</script>

<style scoped>
.job-listing-list { padding: 0; }
.loading, .error { padding: 2rem; text-align: center; }
</style>
