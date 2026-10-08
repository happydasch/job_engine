<template>
  <div class="dashboard-view">
    <!-- ── Onboarding Checklist (shown when setup is incomplete) ── -->
    <OnboardingChecklist />

    <!-- ── Stats Grid (6 cards) ── -->
    <StatsGrid :cards="statCards" :accented="true" />

    <PageTitle title="Dashboard" :subtitle="`${stats.platform_count} sources · ${stats.new_today} new today`" />

    <EmptyState v-if="loading" loading message="Loading dashboard..." />

    <EmptyState v-else-if="loadError" title="Failed to load dashboard" :message="loadError">
      <BaseButton variant="primary" size="sm" @click="loadStats">Retry</BaseButton>
    </EmptyState>

    <EmptyState v-else-if="stats.total_jobs === 0" title="No jobs yet" message="Run scrapers first to populate the dashboard with job data">
      <template #icon>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>
        </svg>
      </template>
    </EmptyState>

    <template v-else>

    <!-- ── Score Breakdown + Market Insights (bottom sections) ── -->
    <DashboardCharts
      :match-dist-buckets="stats.match_dist_buckets"
      :top-skills="topSkills"
      :profile-skills-count="stats.profile_skills_count || 0"
      :jobs-per-run="stats.jobs_per_run || []"
      :remote-pct="stats.remote_pct"
      :hybrid-pct="stats.hybrid_pct"
      :office-pct="stats.office_pct"
      :top-platforms="topPlatforms"
      :critical-gaps="stats.critical_gaps || []"
      :scheduler="stats.scheduler || { enabled: false, interval_minutes: 360 }"
      :total-jobs="stats.total_jobs"
      :platform-count="stats.platform_count"
      :best-match-score="stats.best_match_score"
      :avg-dimensions="stats.avg_dimensions || {}"
      :jobs-with-salary="stats.jobs_with_salary"
      :top-contracts="stats.top_contracts || []"
      :app-funnel="stats.application_funnel || { applied: 0, interview: 0, offer: 0 }"
      :llm-count="stats.llm_count"
      :scraper-health="stats.scraper_health || {}"
    />

    <!-- ── Top Matches + Newest Jobs + Interesting Jobs (3-column) ── -->
    <div class="match-row">

      <!-- ── Top 5 Matches ── -->
      <Card flush class="match-list">
        <SectionHeading title="Top Matches" class="match-list-header">
          <template #action>
            <router-link to="/jobs?sort_by=match_score&amp;sort_order=desc" class="link">View all &rarr;</router-link>
          </template>
        </SectionHeading>
        <template v-if="stats.top_matches?.length">
          <JobListItem v-for="job in stats.top_matches" :key="job.external_id" :job="job" compact />
        </template>
        <EmptyState v-else title="No top matches yet">
          <template #icon>
            <AppIcon name="check" :size="20" :stroke-width="1.5" />
          </template>
        </EmptyState>
      </Card>

      <!-- ── Newest Jobs ── -->
      <Card flush class="match-list">
        <SectionHeading title="Newest Jobs" class="match-list-header">
          <template #action>
            <router-link to="/jobs?sort_by=discovered_at&amp;sort_order=desc" class="link">View all &rarr;</router-link>
          </template>
        </SectionHeading>
        <template v-if="stats.newest_jobs?.length">
          <JobListItem v-for="job in stats.newest_jobs" :key="job.external_id" :job="job" compact :show-location="false" />
        </template>
        <EmptyState v-else title="No new jobs yet">
          <template #icon>
            <AppIcon name="layout" :size="20" :stroke-width="1.5" />
          </template>
        </EmptyState>
      </Card>

      <!-- ── Recently Viewed ── -->
      <Card flush class="match-list">
        <SectionHeading title="Recently Viewed" class="match-list-header">
          <template #action>
            <router-link to="/jobs?sort_by=updated_at&amp;sort_order=desc" class="link">View all &rarr;</router-link>
          </template>
        </SectionHeading>
        <template v-if="recentlyViewedJobs.length">
          <JobListItem v-for="job in recentlyViewedJobs.slice(0, 5)" :key="job.external_id" :job="job" compact />
        </template>
        <EmptyState v-else title="No recently viewed jobs yet">
          <template #icon>
            <AppIcon name="info" :size="20" :stroke-width="1.5" />
          </template>
        </EmptyState>
      </Card>
    </div>

    <!-- ── Needs Follow-up ── -->
    <div v-if="followUpApps.length" class="follow-up-section">
      <Card flush>
        <SectionHeading title="Needs Follow-up" class="match-list-header">
          <template #action>
            <router-link to="/applications" class="link">View all &rarr;</router-link>
          </template>
        </SectionHeading>
        <div class="follow-up-list">
          <div v-for="app in followUpApps" :key="app.id" class="follow-up-item">
            <router-link :to="`/jobs/${app.job_external_id}`" class="link">{{ app.job_title }}</router-link>
            <span class="text-secondary">@ {{ app.company }}</span>
            <span class="follow-up-days">{{ app.days_since_contact }}d since contact</span>
            <BaseButton variant="outline" size="sm" @click="openFollowUp(app)">Log Follow-up</BaseButton>
          </div>
        </div>
      </Card>
    </div></template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useFetch } from '../composables/useFetch'
import { showToast } from '../composables/useToast'
import { useScraperStatusStore } from '../stores/scraperStatus'
import PageTitle from '../components/common/PageTitle.vue'
import StatsGrid from '../components/common/StatsGrid.vue'
import DashboardCharts from '../components/common/DashboardCharts.vue'
import EmptyState from '../components/common/EmptyState.vue'
import BaseButton from '../components/common/BaseButton.vue'
import Card from '../components/common/Card.vue'
import SectionHeading from '../components/common/SectionHeading.vue'
import AppIcon from '../components/common/AppIcon.vue'
import JobListItem from '../components/common/JobListItem.vue'
import OnboardingChecklist from '../components/setup/OnboardingChecklist.vue'
import { useRecentlyViewed } from '../composables/useRecentlyViewed'

const stats = reactive({
  total_jobs: 0, avg_score: 0, high_match_count: 0, platform_count: 0,
  new_today: 0, best_match_score: 0,
  remote_pct: 0, hybrid_pct: 0, office_pct: 0,
  top_matches: [], newest_jobs: [], recent_llm_jobs: [],
  match_dist_buckets: [], top_skills: [], top_platforms: [], jobs_per_run: [],
  avg_dimensions: {}, jobs_with_salary: 0, top_contracts: [],
  application_funnel: { applied: 0, interview: 0, offer: 0 },
  llm_count: 0, scraper_health: {},
})
const loading = ref(true)
const loadError = ref(null)
const { execute: fetchStats } = useFetch('')

const recentlyViewedJobs = useRecentlyViewed()

async function loadStats() {
  loadError.value = null
  try {
    const result = await fetchStats('/api/dashboard/stats')
    if (result) Object.assign(stats, result)
  } catch (e) {
    // Only block the page on the initial load; later background refreshes
    // keep showing the last good data.
    if (!stats.total_jobs) loadError.value = e.message || 'Unknown error'
    console.error('Failed to load dashboard stats:', e)
  }
  loading.value = false
}

// Watch for scraper run completions to refresh dashboard stats
const scraperStore = useScraperStatusStore()
watch(() => scraperStore.lastRunCompletedAt, () => {
  loadStats()
})

// Periodic refresh every 30 seconds as a fallback (catches scheduled/cron runs)
let refreshTimer = null
onMounted(async () => {
  await loadStats()
  await loadFollowUpApps()
  refreshTimer = setInterval(() => loadStats(), 30000)
})
onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

// ── Follow-up tracking ──
const followUpApps = ref([])
const { execute: fetchFollowUp } = useFetch('')

async function loadFollowUpApps() {
  try {
    const result = await fetchFollowUp('/api/applications/follow-up')
    followUpApps.value = result || []
  } catch (e) {
    console.error('Failed to load follow-up apps:', e)
  }
}

function openFollowUp(app) {
  const note = prompt(`Log follow-up note for "${app.job_title}":`, '')
  if (note === null) return
  fetch(`/api/applications/${app.id}/follow-up`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes: note || '' }),
  }).then(async (res) => {
    if (!res.ok) throw new Error(`Follow-up failed: ${res.status}`)
    showToast('Follow-up logged', 'success')
    await loadFollowUpApps()
  }).catch((e) => {
    showToast(e.message || 'Failed to log follow-up', 'error')
  })
}

const statCards = computed(() => {
  const s = stats
  const pct = (v) => {
    if (v >= 70) return 'success'
    if (v >= 40) return 'warning'
    return 'danger'
  }
  return [
    { label: 'Avg Match', value: s.avg_score + '%', variant: pct(s.avg_score) },
    { label: 'Best Match', value: s.best_match_score + '%', variant: 'success' },
    { label: 'High Matches', value: s.high_match_count, variant: 'success' },
    { label: 'Platforms', value: s.platform_count, variant: 'primary' },
    { label: 'New Today', value: s.new_today, variant: 'primary' },
    { label: 'Total Jobs', value: s.total_jobs, variant: 'primary' },
  ]
})

const topPlatforms = computed(() => (stats.top_platforms || []).slice(0, 8).map(p => ({ name: p[0], count: p[1] })))
// Hoisted from the template — stable array identity so the 1,027-line
// DashboardCharts component doesn't re-render on every parent tick
const topSkills = computed(() => (stats.top_skills || []).map(s => ({ name: s[0], count: s[1] })))
</script>

<style scoped>
.loading { padding: 2rem; text-align: center; }
.match-list { margin-bottom: 1.5rem; }
.match-list-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--color-border, #e2e8f0);
  font-size: 0.875rem; font-weight: 600; margin-bottom: 0;
}
.match-list-header :deep(.section-title) { font-size: 0.875rem; font-weight: 600; }
.match-list-header .link { font-size: 0.8125rem; font-weight: 500; }
.match-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1.5rem; }
.match-row .match-list { margin-bottom: 0; }

@media (max-width: 1100px) {
  .match-row { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 640px) {
  .match-row { grid-template-columns: 1fr; }
}

/* ── Follow-up section ── */
.follow-up-section { margin-top: 1.5rem; margin-bottom: 1.5rem; }
.follow-up-list { padding: 0.5rem 0.75rem; }
.follow-up-item {
  display: flex; align-items: center; gap: 0.75rem;
  padding: 0.5rem 0; font-size: 0.8125rem;
  border-bottom: 1px solid var(--border, #e2e8f0);
}
.follow-up-item:last-child { border-bottom: none; }
.follow-up-days {
  font-size: 0.75rem; color: var(--color-text-secondary, #64748b);
  margin-left: auto; white-space: nowrap;
}
@media (max-width: 480px) {
  .match-list-header { flex-direction: column; align-items: flex-start; gap: 0.25rem; }
}
</style>