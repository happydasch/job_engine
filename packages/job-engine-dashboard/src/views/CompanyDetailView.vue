<template>
  <div class="company-detail-view">
    <div v-if="loading" class="loading-state">
      <div class="skeleton-block" style="height: 28px; width: 200px; margin-bottom: 1.5rem;"></div>
      <div class="skeleton-block" style="height: 64px; width: 300px; margin-bottom: 2rem;"></div>
      <div class="skeleton-block" style="height: 200px;"></div>
    </div>
    <div v-else-if="error" class="error-state">
      <div class="error-icon"><AppIcon name="alert-triangle" :size="40" :stroke-width="1.5" /></div>
      <h3>Failed to load company</h3>
      <p class="error-detail">{{ error }}</p>
      <router-link to="/companies" class="back-link"><AppIcon name="arrow-left" :size="13" /> Back to Companies</router-link>
    </div>
    <template v-else-if="company">
      <router-link to="/companies" class="back-link"><AppIcon name="arrow-left" :size="13" /> Back to Companies</router-link>
      <Card class="topbar-card">
        <div class="card-header topbar-header">
          <div class="company-icon-large" :style="{ background: companyColor }">{{ initials }}</div>
          <div class="topbar-info">
            <h1 class="topbar-title">{{ company.name }}</h1>
            <div class="hero-meta-tags">
              <span v-if="company.industry" class="hero-tag">{{ company.industry }}</span>
              <span v-if="company.headquarters" class="hero-tag">{{ company.headquarters }}</span>
              <span v-if="company.size_range" class="hero-tag">{{ company.size_range }} employees</span>
              <span v-if="company.founded_year" class="hero-tag">Founded {{ company.founded_year }}</span>
              <span class="hero-tag hero-tag--accent">{{ company.job_count || 0 }} listing{{ company.job_count === 1 ? '' : 's' }}</span>
              <span class="hero-tag hero-tag--accent">{{ platformCount }} platform{{ platformCount === 1 ? '' : 's' }}</span>
              <span v-if="company.created_at" class="hero-tag hero-tag--accent">Tracked {{ formatDate(company.created_at) }}</span>
            </div>
          </div>
        </div>
      </Card>

      <!-- About Section -->
      <section v-if="company.description" class="detail-section">
        <h2 class="section-title">About</h2>
        <div class="about-card">
          <p class="description-text">{{ company.description }}</p>
        </div>
      </section>

      <!-- Job Listings -->
      <div class="company-jobs-section">
        <SectionHeading title="Job Listings" :count="company.jobs?.length || null" />
        <Card flush class="job-listing-list" v-if="company.jobs?.length">
          <JobCard v-for="job in company.jobs" :key="job.external_id" :job="job" @toggle-fav="handleToggleFav" @toggle-hide="handleToggleHide" />
        </Card>
        <EmptyState v-else
          title="No job listings"
          message="This company currently has no imported job listings. Run scrapers to discover their openings."
        >
          <template #icon>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>
            </svg>
          </template>
        </EmptyState>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useFetch } from '../composables/useFetch'
import { useJobActions } from '../composables/useJobActions'
import JobCard from '../components/jobs/JobCard.vue'
import EmptyState from '../components/common/EmptyState.vue'
import SectionHeading from '../components/common/SectionHeading.vue'
import Card from '../components/common/Card.vue'
import AppIcon from '../components/common/AppIcon.vue'
import { useDateTime } from '../composables/useDateTime'


const route = useRoute()

const company = ref(null)
const loading = ref(true)
const error = ref(null)
const { execute: fetchCompanyApi } = useFetch('')

const initials = computed(() => {
  if (!company.value?.name) return '??'
  return company.value.name.slice(0, 2).toUpperCase()
})

const companyColor = computed(() => {
  if (!company.value?.name) return '#3b82f6'
  const colors = ['#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#ec4899', '#f43f5e', '#ef4444', '#f97316', '#eab308', '#22c55e', '#14b8a6', '#06b6d4']
  let hash = 0
  for (let i = 0; i < company.value.name.length; i++) {
    hash = company.value.name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
})

const platformCount = computed(() => {
  if (!company.value?.jobs?.length) return 0
  const platforms = new Set(company.value.jobs.map(j => j.platform).filter(Boolean))
  return platforms.size
})

// Dynamic tab title — watch AFTER company ref is declared
watch(company, (c) => {
  if (c?.name) document.title = `Job Engine - ${c.name}`
}, { immediate: true })

const { formatDate } = useDateTime()

const { toggleFav: handleToggleFav, toggleHide: handleToggleHide } = useJobActions(
  (id) => company.value?.jobs?.find(j => j.external_id === id)
)

onMounted(async () => {
  try {
    const result = await fetchCompanyApi(`/api/companies/${route.params.id}`)
    company.value = result
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
/* ── Loading / Error ── */
.loading-state, .error-state { padding: 3rem 2rem; text-align: center; }
.error-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
.error-state h3 { font-size: 1.125rem; font-weight: 600; margin: 0 0 0.5rem; }
.error-detail { color: var(--color-text-secondary, #64748b); font-size: 0.875rem; margin: 0 0 1rem; }
.skeleton-block { background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 8px; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* ── Topbar card (matches job detail) ── */
.topbar-card { margin-bottom: 1.5rem; }
.topbar-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}
.back-link {
  display: inline-block;
  margin-bottom: 0.75rem;
  font-size: 0.8125rem;
  color: var(--color-primary, #3b82f6);
  text-decoration: none;
  font-weight: 500;
}
.back-link:hover { text-decoration: underline; }
.topbar-title {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0 0 0.25rem;
}
.topbar-info { flex: 1; min-width: 0; }
.company-icon-large {
  width: 52px; height: 52px; border-radius: 11px;
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 1.125rem; font-weight: 700; flex-shrink: 0; letter-spacing: 0.04em;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}
.hero-meta-tags { display: flex; flex-wrap: wrap; gap: 0.375rem; }
.hero-tag {
  display: inline-block; padding: 1px 8px; border-radius: 20px;
  font-size: 0.6875rem; font-weight: 500; color: #475569;
  background: var(--gray-100, #f1f5f9);
}
.hero-tag--accent {
  background: var(--color-primary-10, rgba(37, 99, 235, 0.1));
  color: var(--color-primary, #3b82f6);
}
.hero-tag--accent strong { font-weight: 700; }

/* ── Sections ── */
.detail-section { margin-bottom: 1rem; }
.section-title { font-size: 1rem; font-weight: 600; margin: 0 0 0.5rem; }
.about-card {
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e2e8f0); border-radius: 8px; padding: 0.875rem;
}
.description-text { color: var(--color-text-secondary, #64748b); font-size: 0.8125rem; line-height: 1.6; margin: 0; white-space: pre-line; }

/* ── Job Listings Section ── */
.company-jobs-section { margin-top: 0.25rem; }
.job-listing-list { padding: 0; }
@media (max-width: 600px) {
  .hero-meta-tags { justify-content: center; }
}
</style>