<template>
  <div class="job-detail-view">
    <EmptyState v-if="loading" loading message="Loading job..." />
    <div v-else-if="error" class="error">{{ error }}</div>
    <EmptyState v-else-if="!job" title="Job not found" message="This job could not be found. It may have been removed or the link is invalid.">
      <template #icon>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>
        </svg>
      </template>
    </EmptyState>
    <template v-else-if="job">
      <router-link to="/jobs" class="back-link"><AppIcon name="arrow-left" :size="13" /> Back to Jobs</router-link>
      <!-- Top bar card -->
      <Card class="topbar-card">
        <div class="card-header topbar-header">
          <h1 class="topbar-title">
            {{ job.title }}
            <a v-if="job.url" :href="job.url" target="_blank" rel="noopener" class="link-icon" title="Open offer" aria-label="Open offer in new tab"><AppIcon name="external-link" :size="13" /></a>
          </h1>
          <ScoreBadge :score="job.match_score || 0" variant="pill" />
          <JobFavHideButtons
            :job="job"
            :disabled="isBusy"
            @toggle-fav="onToggleFav"
            @toggle-hide="onToggleHide"
          />
        </div>
        <div class="card-body topbar-actions">
          <BaseButton class="btn-fetch" :data-job-id="job.external_id" :loading="fetchBusy" :disabled="isBusy" @click="onFetchContent">
            {{ fetchBusy ? 'Fetching...' : (job.fetched_content ? 'Re-fetch &amp; Analyze' : 'Fetch &amp; Analyze') }}
          </BaseButton>
          <BaseButton variant="success" class="btn-apply" :data-job-id="job.external_id" @click="onApply" :disabled="isBusy" title="Apply to this job">Apply</BaseButton>
          <router-link
            v-if="job.application_status"
            :to="'/applications?job_id=' + job.id"
            class="application-badge status-badge"
            :class="'status-' + job.application_status"
          >
            {{ job.application_status }}
          </router-link>
        </div>
      </Card>

      <div class="detail-body">
        <!-- LEFT COLUMN: AI analysis -->
        <div class="detail-left">
          <AiAnalysisPane :key="'ai-' + analysisKey" :job-id="job.external_id" :application-id="job.application_id" :parent-busy="fetchBusy" @busy-change="aiBusy = $event" @refresh="onFetchContent" />
        </div>

        <!-- RIGHT COLUMN: Details + Match Breakdown (simplified) -->
        <div class="detail-right">
          <Card class="detail-card">
            <h2>Details <small v-if="job.discovered_at">discovered {{ job.discovered_at.slice(0, 10) }}</small></h2>
            <div class="detail-fields-grid">
              <div class="detail-field" v-if="job.platform">
                <span class="detail-field-label">Platform</span>
                <span class="detail-field-value">
                  <router-link :to="'/jobs?platform=' + encodeURIComponent(job.platform)" class="detail-link">{{ job.platform }}</router-link>
                </span>
              </div>
              <div class="detail-field" v-if="job.company">
                <span class="detail-field-label">Company</span>
                <span class="detail-field-value">
                  <router-link :to="'/companies/' + job.company_id" class="detail-link">{{ job.company }}</router-link>
                </span>
              </div>
              <div class="detail-field" v-if="job.location">
                <span class="detail-field-label">Location</span>
                <span class="detail-field-value">
                  <router-link :to="'/jobs?location=' + encodeURIComponent(job.location)" class="detail-link">{{ job.location }}</router-link>
                </span>
              </div>
              <div class="detail-field" v-if="job.remote !== undefined">
                <span class="detail-field-label">Remote</span>
                <span class="detail-field-value">{{ job.remote ? 'Yes' : 'No' }}</span>
              </div>
              <div class="detail-field" v-if="job.salary_min || job.salary_max">
                <span class="detail-field-label">Salary</span>
                <span class="detail-field-value"><div class="salary-stacked">
                  <span class="salary-source">{{ salaryParts.source }}</span>
                  <span v-if="salaryParts.converted" class="salary-converted">≈{{ salaryParts.converted }}</span>
                </div></span>
              </div>
              <div class="detail-field" v-if="job.category">
                <span class="detail-field-label">Category</span>
                <span class="detail-field-value">
                  <router-link :to="'/jobs?category=' + encodeURIComponent(job.category)" class="detail-link">{{ job.category }}</router-link>
                </span>
              </div>
              <div class="detail-field" v-if="job.experience_level">
                <span class="detail-field-label">Experience</span>
                <span class="detail-field-value">
                  <router-link :to="'/jobs?experience_level=' + encodeURIComponent(job.experience_level)" class="detail-link">{{ getExperienceLabel(job.experience_level) }}</router-link>
                </span>
              </div>
              <div class="detail-field" v-if="job.contract_type">
                <span class="detail-field-label">Contract</span>
                <span class="detail-field-value">
                  <router-link :to="'/jobs?contract_type=' + encodeURIComponent(job.contract_type)" class="detail-link">{{ getContractLabel(job.contract_type) }}</router-link>
                </span>
              </div>
              <!-- Skills -->
              <div class="detail-field" v-if="job.skills?.length">
                <span class="detail-field-label">Skills</span>
                <span class="detail-field-value">
                  <div class="skills-list">
                    <span v-for="s in job.skills" :key="s" class="skill-tag-wrapper">
                      <button type="button" class="skill-tag skill-link" @click="showSkillMenu($event, s)">{{ s }}</button>
                    </span>
                  </div>
                </span>
              </div><!-- Skill category popover -->
              <Teleport to="body">
                <div v-if="skillMenu" class="skill-popover" :style="{ position: 'fixed', left: skillMenu.x + 'px', top: skillMenu.y + 'px' }">
                  <div class="skill-popover-title">Add "{{ skillMenu.skill }}" to…</div>
                  <button v-for="cat in skillCategories" :key="cat"
                    class="skill-popover-btn"
                    :class="{ 'skill-popover-btn--exists': existsInProfile(skillMenu.skill, cat) }"
                    @click="addSkillToProfile(skillMenu.skill, cat)">
                    <span class="skill-popover-icon"><AppIcon :name="existsInProfile(skillMenu.skill, cat) ? 'check' : 'plus'" :size="11" /></span>
                    {{ cat }}
                  </button>
                  <div class="skill-popover-divider"></div>
                  <button class="skill-popover-btn skill-popover-btn--search"
                    @click="searchJobs(skillMenu.skill)">Search Jobs</button>
                </div>
              </Teleport>
            </div>

            <!-- Match Breakdown (inline, compact) -->
            <MatchBreakdown v-if="job.match_details" :details="job.match_details" />
          </Card>
        </div>
      </div>

      <!-- Raw fetched content (collapsible) -->
      <details v-if="job.fetched_content" class="raw-content">
        <summary class="raw-content-summary">
          <span class="raw-content-label">Raw Fetched Content</span>
          <span class="raw-content-size">{{ (job.fetched_content.length / 1024).toFixed(1) }} KB</span>
        </summary>
        <pre class="raw-content-body">{{ job.fetched_content }}</pre>
      </details>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getExperienceLabel, getContractLabel } from '../constants/enums.js'
import { useRoute, useRouter } from 'vue-router'
import { useFetch } from '../composables/useFetch'
import { useApplicationStatus } from '../composables/useApplicationStatus'
import { useExchangeRates } from '../composables/useExchangeRates'
import { recordJobView } from '../composables/useRecentlyViewed'
import { showToast } from '../composables/useToast'
import { useTaskPoll } from '../composables/useTaskPoll'
import { useJobActions } from '../composables/useJobActions'
import { useAddToProfile } from '../composables/useAddToProfile'
import MatchBreakdown from '../components/job-detail/MatchBreakdown.vue'
import AiAnalysisPane from '../components/job-detail/AiAnalysisPane.vue'
import BaseButton from '../components/common/BaseButton.vue'
import Card from '../components/common/Card.vue'
import EmptyState from '../components/common/EmptyState.vue'
import AppIcon from '../components/common/AppIcon.vue'
import ScoreBadge from '../components/common/ScoreBadge.vue'
import JobFavHideButtons from '../components/jobs/JobFavHideButtons.vue'

const route = useRoute()
const router = useRouter()
const { createApplication } = useApplicationStatus()
const { getSalaryParts } = useExchangeRates()

const salaryParts = computed(() => {
  return getSalaryParts(job.value?.salary_min, job.value?.salary_max, job.value?.currency)
})
const job = ref(null)
const loading = ref(true)
const error = ref(null)
const analysisKey = ref(0)
const fetchBusy = ref(false)   // fetch-content operation
const aiBusy = ref(false)      // AI analysis operations (child component)
const operationBusy = ref(false) // other operations (fav, hide, apply)
const isBusy = computed(() => fetchBusy.value || aiBusy.value || operationBusy.value)

const { toggleFav, toggleHide } = useJobActions(() => job.value)

// Background LLM task triggered by fetch-content — polled via shared useTaskPoll
const fetchTaskId = ref(null)
const { status: fetchTaskStatus, error: fetchTaskError, stop: stopFetchPoll } = useTaskPoll(fetchTaskId)
let fetchTimeout = null

watch(fetchTaskStatus, async (st) => {
  if (st === 'completed') {
    clearTimeout(fetchTimeout)
    await finishFetch()
  } else if (st === 'failed') {
    clearTimeout(fetchTimeout)
    error.value = fetchTaskError.value || 'LLM analysis failed'
    failFetch()
  }
})

async function finishFetch() {
  try {
    const { execute: refetch } = useFetch(`/api/jobs/${route.params.id}`)
    job.value = await refetch()
  } catch (e) {
    error.value = e.message
  }
  analysisKey.value++
  fetchBusy.value = false
}

function failFetch() {
  analysisKey.value++ // Re-create child component so it resets its busy state
  fetchBusy.value = false
}

// Skill category popover
const skillMenu = ref(null) // { x, y, skill } or null
const { skillCategories, loadProfileData: loadSkillCategories, existsInProfile: existsInProfileShared, addToProfile } = useAddToProfile()

function existsInProfile(skill, subKey) {
  return existsInProfileShared(skill, 'skills', subKey)
}

function showSkillMenu(event, skill) {
  const rect = event.currentTarget.getBoundingClientRect()
  skillMenu.value = { x: rect.left, y: rect.bottom + 4, skill }
}

function closeSkillMenu() {
  skillMenu.value = null
}

function onDocClickSkill(event) {
  if (!skillMenu.value) return
  if (event.target.closest('.skill-tag')) return
  const popover = document.querySelector('.skill-popover')
  if (popover && !popover.contains(event.target)) {
    closeSkillMenu()
  }
}

async function addSkillToProfile(skill, subKey) {
  closeSkillMenu()
  await addToProfile('skills', skill, subKey)
}

function searchJobs(skill) {
  closeSkillMenu()
  router.push({ path: '/jobs', query: { skill } })
}

// Dynamic tab title
watch(job, (j) => {
  if (j?.title) document.title = `Job Engine - ${j.title}`
}, { immediate: true })

onMounted(async () => {
  // Load profile for currency conversion
  useExchangeRates().loadProfile()
  await reloadJob()
  loading.value = false
  loadSkillCategories()
  document.addEventListener('click', onDocClickSkill)
})

// Stop polling if the user navigates away while a fetch is running
onUnmounted(() => {
  clearTimeout(fetchTimeout)
  document.removeEventListener('click', onDocClickSkill)
})

async function onToggleFav() {
  operationBusy.value = true
  try { await toggleFav(job.value.external_id) }
  finally { operationBusy.value = false }
}

async function onToggleHide() {
  operationBusy.value = true
  try { await toggleHide(job.value.external_id) }
  finally { operationBusy.value = false }
}

async function onFetchContent() {
  fetchBusy.value = true
  error.value = null
  try {
    const { execute } = useFetch(`/api/jobs/${job.value.external_id}/fetch-content`, { method: 'POST' })
    const result = await execute()
    // If a background LLM task was triggered, hand polling over to the
    // useTaskPoll watcher above (with a client-side timeout — the task
    // keeps running server-side so its result can still be cached)
    if (result?.task_id) {
      fetchTimeout = setTimeout(() => {
        stopFetchPoll()
        error.value = 'LLM analysis timed out'
        failFetch()
      }, 300000) // 5 min timeout for LLM
      fetchTaskId.value = result.task_id
      return
    }
    await finishFetch()
  } catch (e) {
    console.error('Fetch content failed:', e)
    error.value = error.value || e.message
    fetchBusy.value = false
  }
}

async function onApply() {
  operationBusy.value = true
  try {
    await createApplication(job.value.external_id)
    // Reload full job data from the API — this is the source of truth for
    // application_status/application_id, not the create endpoint's response
    // (which returns an operation status like "created"/"exists", not the
    // application's lifecycle status).
    await reloadJob()
  } catch (e) {
    showToast(`Failed to record application: ${e.message}`, 'error')
  }
  finally { operationBusy.value = false }
}

async function reloadJob() {
  try {
    const { execute } = useFetch(`/api/jobs/${route.params.id}`)
    job.value = await execute()
    recordJobView(job.value)
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.back-link {
  display: inline-block;
  margin-bottom: 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
}

/* ── Topbar ── */
.topbar-card { margin-bottom: 20px; }
.topbar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}
.topbar-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1 1 auto;
  min-width: 40px;
}
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.link-icon {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  margin-left: 3px;
}
.link-icon:hover { color: var(--primary, #2563eb); }

/* ── Detail body layout ── */
.detail-body {
  display: grid;
  grid-template-columns: 3fr 1fr;
  gap: 16px;
}

/* ── Detail card section heading ── */
.detail-card h2 {
  font-size: 14px;
  font-weight: 600;
  margin-top: 0;
  margin-bottom: 14px;
  color: var(--text, #1e293b);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.detail-card h2 small {
  font-weight: 400;
  text-transform: none;
  letter-spacing: normal;
  color: var(--text-secondary, #64748b);
  font-size: 11px;
  margin-left: 4px;
}

.detail-card {
  position: relative;
  padding: 20px;
}
.detail-fields-grid {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.detail-field {
  display: flex;
  flex-direction: column;
  padding: 6px 0;
  border-bottom: 1px solid var(--border, #e2e8f0);
}
.detail-field:last-child { border-bottom: none; }
.detail-field-label {
  font-size: 10px;
  letter-spacing: 0.3px;
  margin-bottom: 1px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary, #64748b);
}
.detail-field-value {
  font-size: 13px;
  color: var(--text, #1e293b);
}

/* Skill tags in detail */
.skill-tag {
  display: inline-block;
  padding: 2px 8px;
  margin: 2px;
  background: var(--primary-08, rgba(37, 99, 235, 0.08));
  color: var(--primary, #2563eb);
  border: none;
  font-family: inherit;
  border-radius: 12px;
  font-size: 10px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.skill-tag:hover { background: var(--primary-18, rgba(37, 99, 235, 0.18)); }

.skill-tag-wrapper {
  display: inline-flex;
  align-items: center;
  margin: 2px;
}

/* ── Skill category popover ── */
.skill-popover {
  z-index: 1000;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 170px;
  overflow: hidden;
}
.skill-popover-title {
  padding: 8px 12px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary, #64748b);
  border-bottom: 1px solid var(--color-border, #e2e8f0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.skill-popover-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 0;
  background: transparent;
  font-family: inherit;
  font-size: 0.8125rem;
  color: var(--color-text, #1e293b);
  cursor: pointer;
  text-align: left;
  transition: background 0.1s;
}
.skill-popover-btn:hover {
  background: var(--color-bg-subtle, #f1f5f9);
}
.skill-popover-btn--exists {
  color: var(--color-success, #16a34a);
  font-weight: 600;
}
.skill-popover-icon {
  font-size: 0.75rem;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}
.skill-popover-divider {
  height: 1px;
  background: var(--color-border, #e2e8f0);
  margin: 0;
}
.skill-popover-btn--search {
  color: var(--color-primary, #3b82f6);
}

/* Application badge (status pill in topbar) */
.application-badge {
  display: inline-block;
  padding: 6px 14px;
  border-radius: var(--radius, 8px);
  font-size: 12px;
  font-weight: 600;
  text-transform: capitalize;
}
.application-badge:hover { opacity: 0.85; }

/* ── Topbar buttons (fetch) — compact on BaseButton ── */
.topbar-actions .btn-fetch {
  background: var(--primary, #2563eb);
  color: white;
  border-color: var(--primary, #2563eb);
}
.topbar-actions .btn-fetch:hover:not(:disabled) {
  background: var(--primary-light, #3b82f6);
}
.topbar-actions .btn-fetch:disabled,
.topbar-actions .btn-apply:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 840px) {
  .detail-body { grid-template-columns: 1fr; }
  .topbar-header { gap: 6px; }
  .topbar-actions { flex-wrap: wrap; }
  .topbar-card { margin-bottom: 12px; }
}

@media (max-width: 640px) {
  .topbar-header { flex-wrap: wrap; }
}

@media (max-width: 480px) {
  .topbar-header { gap: 4px; }
  .topbar-title {
    width: 100%;
    flex: none;
    font-size: 14px;
    white-space: normal;
    overflow: visible;
    text-overflow: unset;
    margin-bottom: 4px;
  }
  .topbar-actions {
    gap: 6px;
    margin-top: 8px;
  }
  .topbar-actions .btn-fetch,
  .topbar-actions .btn-apply {
    font-size: 11px;
    padding: 4px 10px;
    min-height: 34px;
  }
  .detail-card { padding: 14px; }
  .detail-card h2 { font-size: 12px; }
  .detail-card h2 small { font-size: 10px; }
  .detail-field { padding: 4px 0; }
  .detail-field-value { font-size: 12px; }
  .back-link { font-size: 0.75rem; margin-bottom: 0.5rem; }
}

/* ── Detail Links ── */
.detail-link {
  font-weight: 500;
  transition: color 0.15s;
}
.loading, .error { padding: 2rem; text-align: center; }
.salary-stacked { display: inline-flex; flex-direction: column; gap: 0; line-height: 1.3; }
.salary-stacked .salary-converted { font-weight: 500; font-size: 0.75rem; color: var(--color-text-secondary, #64748b); }

/* ── Raw Fetched Content ── */
.raw-content {
  margin-top: 1.5rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 0.5rem;
  overflow: hidden;
  background: var(--color-bg-card, #fff);
}
.raw-content-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 600;
  background: var(--color-bg-subtle, #f8fafc);
  border-bottom: 1px solid transparent;
  user-select: none;
}
.raw-content[open] .raw-content-summary {
  border-bottom-color: var(--color-border, #e2e8f0);
}
.raw-content-label {
  color: var(--color-text, #1e293b);
}
.raw-content-size {
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--color-text-secondary, #64748b);
  margin-left: auto;
}
.raw-content-body {
  margin: 0;
  padding: 1rem;
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
  font-size: 0.8125rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
  max-height: 70vh;
  overflow-y: auto;
  color: var(--color-text, #1e293b);
  background: var(--color-bg, #fafafa);
}
</style>