<template>
  <div class="companies-view">
    <PageTitle title="Companies" :count="companyCountString" />

    <FilterPanel
      v-model="filters.search"
      placeholder="Search companies by name, industry, or location..."
      show-search-icon
      :show-reset="true"
      :has-active-filters="hasActiveFilters"
      @search="fetchCompanies"
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
    </FilterPanel>
    <SectionHeading title="Companies" :count="companies.length || null" />



    <div v-if="loading" class="loading-state">
      <div class="skeleton-grid">
        <div v-for="i in 6" :key="i" class="skeleton-card">
          <div class="skeleton-row" style="width: 48px; height: 48px; border-radius: 10px;"></div>
          <div class="skeleton-row" style="width: 70%; height: 14px;"></div>
          <div class="skeleton-row" style="width: 50%; height: 12px;"></div>
        </div>
      </div>
    </div>
    <div v-else-if="error" class="error-state">
      <div class="error-icon"><AppIcon name="alert-triangle" :size="40" :stroke-width="1.5" /></div>
      <h3>Failed to load companies</h3>
      <p class="error-detail">{{ error }}</p>
      <BaseButton variant="primary" @click="fetchCompanies">Retry</BaseButton>
    </div>
    <EmptyState v-else-if="!companies.length && search"
      title="No companies match your search"
      :message="`No results for '${search}'. Try a different search term or clear the filter`"
    >
      <template #icon>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
        </svg>
      </template>
    </EmptyState>
    <EmptyState v-else-if="!companies.length"
      title="No companies yet"
      message="Run scrapers first to populate companies"
    >
      <template #icon>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>
        </svg>
      </template>
    </EmptyState>
    <div v-else class="companies-grid">
      <CompanyCard v-for="c in companies" :key="c.id" :company="c" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useFetch } from '../composables/useFetch'
import { useFilters } from '../composables/useFilters'
import { useRefreshOnScrapeComplete } from '../composables/useRefreshOnScrapeComplete'
import EmptyState from '../components/common/EmptyState.vue'
import PageTitle from '../components/common/PageTitle.vue'
import FilterPanel from '../components/common/FilterPanel.vue'
import CompanyCard from '../components/companies/CompanyCard.vue'
import AppIcon from '../components/common/AppIcon.vue'
import FilterSortSelect from '../components/common/filters/FilterSortSelect.vue'

const companies = ref([])
const totalCount = ref(null)
const loading = ref(false)
const error = ref(null)

const { filters, hasActiveFilters, reset } = useFilters({
  search: '',
  sortBy: 'name',
  sortOrder: 'asc',
}, 'job_engine_companies_filters')
const { execute: fetchCompaniesApi } = useFetch('')

const companyCountString = computed(() => {
  if (totalCount.value === null) return null
  return `${totalCount.value} compan${totalCount.value === 1 ? 'y' : 'ies'}`
})

const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'job_count', label: 'Listings' },
]

async function fetchCompanies() {
  loading.value = true; error.value = null
  try {
    const params = new URLSearchParams()
    if (filters.search) params.set('q', filters.search)
    params.set('sort_by', filters.sortBy)
    params.set('sort_order', filters.sortOrder)
    const result = await fetchCompaniesApi(`/api/companies?${params.toString()}`)
    companies.value = result
    totalCount.value = companies.value.length
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onReset() {
  reset()
  fetchCompanies()
}

function toggleSortOrder() {
  filters.sortOrder = filters.sortOrder === 'asc' ? 'desc' : 'asc'
  fetchCompanies()
}

onMounted(() => fetchCompanies())

// Re-fetch when a scrape run adds/removes companies
useRefreshOnScrapeComplete(() => fetchCompanies())
</script>

<style scoped>
/* ── Loading / Error ── */
.loading-state, .error-state { padding: 2rem; text-align: center; }
.error-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
.error-state h3 { font-size: 1.125rem; font-weight: 600; margin: 0 0 0.5rem; }
.error-detail { color: var(--color-text-secondary, #64748b); font-size: 0.875rem; margin: 0 0 1rem; }
.skeleton-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
.skeleton-card {
  background: var(--color-bg-card, #fff); border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px; padding: 1.25rem;
  display: flex; flex-direction: column; gap: 0.75rem;
}
.skeleton-row {
  background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 200% 100%; animation: shimmer 1.5s infinite;
  border-radius: 6px;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* ── Grid ── */
.companies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}
.loading, .error { padding: 2rem; text-align: center; }


</style>