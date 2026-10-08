<template>
  <div
    class="job-card job-card--listing"
    :class="{ 'job-card--hidden': job.hidden, 'job-card--favorited': job.favorite }"
    :data-job-id="job.external_id"
  >
    <!-- Left column: Score ring + Salary -->
    <div class="match-left-column">
      <ScoreBadge :score="job.match_score || 0" size="48" />
      <span v-if="job.salary_min || job.salary_max" class="rate-badge rate-badge--below-ring">
        <span class="salary-source">{{ salaryParts.source }}</span>
        <span v-if="salaryParts.converted" class="salary-converted">≈{{ salaryParts.converted }}</span>
      </span>
    </div>
    <div class="job-card-info">
      <!-- Row 1: Title + Actions -->
      <div class="title-row">
        <div class="title">
          <router-link :to="'/jobs/' + encodeURIComponent(job.external_id)" class="link">{{ job.title }}</router-link>
        </div>
        <div class="actions">
          <span v-if="hasAnalysis" class="analysis-dot" title="Has AI analysis"></span>
          <span v-else-if="showFetchedBadge" class="status-badge fetched">Fetched</span>
          <ApplicationStatusDropdown
            :status="job.application_status || ''"
            :app-id="job.application_id"
            :job-external-id="job.external_id"
            :transitions="getValidTransitions(job.application_status)"
            @apply="(jobId) => $emit('apply', jobId)"
            @transition="(payload) => $emit('transition', payload)"
            @reopen="(appId) => $emit('reopen', appId)"
            @delete="(appId) => $emit('delete', appId)"
          >
            <template #trigger="{ toggle, clickable }">
              <button
                type="button"
                class="status-badge status-badge--clickable"
                :class="job.application_id ? 'status-' + job.application_status : 'status-applied'"
                title="Apply"
                @click="toggle"
              >{{ job.application_id ? job.application_status : 'Apply' }}</button>
            </template>
          </ApplicationStatusDropdown>
          <JobFavHideButtons
            :job="job"
            @toggle-fav="(id) => $emit('toggle-fav', id)"
            @toggle-hide="(id) => $emit('toggle-hide', id)"
          />
        </div>
      </div>
      <!-- Row 2: Company, Platform, Location/Remote, Badges -->
      <div class="meta meta-row">
        <span>{{ job.company || 'Unknown company' }}</span>
        <router-link
          :to="'/jobs?platform=' + encodeURIComponent(job.platform)"
          class="link-secondary"
        >{{ (job.platform || '').replace('.com','').replace('.it','').replace('.co','') }}</router-link>
        <span v-if="job.remote" class="job-listing-badge">Remote</span>
        <span v-else>{{ job.location || 'Unknown location' }}</span>
        <span v-if="contractBadge" class="job-listing-badge" :class="contractBadge.class">{{ contractBadge.label }}</span>
        <span v-if="expBadge" class="job-listing-badge" :class="expBadge.class">{{ expBadge.label }}</span>
        <span v-if="job.hidden" class="status-badge archived">hidden</span>
      </div>
      <!-- Row 3: Skills -->
      <div v-if="job.skills?.length" class="job-card-tags">
        <router-link
          v-for="skill in job.skills"
          :key="skill"
          :to="'/jobs?skill=' + encodeURIComponent(skill)"
          class="skill-tag skill-link"
        >{{ skill }}</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { getExperienceLabel, getContractLabel } from '../../constants/enums.js'
import { useExchangeRates } from '../../composables/useExchangeRates'
import { getValidTransitions } from '../../composables/useApplicationStatus'
import ScoreBadge from '../common/ScoreBadge.vue'
import ApplicationStatusDropdown from '../applications/ApplicationStatusDropdown.vue'
import JobFavHideButtons from './JobFavHideButtons.vue'

const props = defineProps({ job: { type: Object, required: true } })
defineEmits(['toggle-fav', 'toggle-hide', 'apply', 'transition', 'reopen', 'delete'])

const { getSalaryParts } = useExchangeRates()

onMounted(() => {
  // Lazy-init: profile data will be fetched once and shared across all components
  useExchangeRates().loadProfile()
})

const salaryParts = computed(() => {
  return getSalaryParts(props.job.salary_min, props.job.salary_max, props.job.currency)
})

const hasAnalysis = computed(() => {
  const a = props.job.llm_analysis
  return a && a !== '' && a !== '{}' && a !== 'null'
})

const showFetchedBadge = computed(() => {
  return props.job.fetched_content && !hasAnalysis.value
})

const contractBadge = computed(() => {
  const ct = (props.job.contract_type || '').toLowerCase()
  if (!ct) return null
  const label = getContractLabel(ct)
  if (ct === 'b2b') return { class: 'b2b', label }
  if (ct === 'permanent' || ct === 'uop') return { class: 'permanent', label }
  if (ct === 'contract' || ct === 'uz') return { class: 'contract', label }
  if (ct === 'mandate') return { class: 'mandate', label }
  return { class: 'other', label }
})

const expBadge = computed(() => {
  const el = (props.job.experience_level || '').toLowerCase()
  if (!el) return null
  const label = getExperienceLabel(el)
  if (/junior|jr|entry/.test(el)) return { class: 'junior', label }
  if (/mid|regular|intermediate/.test(el)) return { class: 'mid', label }
  if (/senior|sr|staff/.test(el)) return { class: 'senior', label }
  if (/lead|principal|head/.test(el)) return { class: 'lead', label }
  if (/executive|director|c-level|cfo|cto/.test(el)) return { class: 'executive', label }
  return { class: 'other', label }
})
</script>

<style scoped>
/* ── Match item (job listing card) ── */
.job-card {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border, #e2e8f0);
  display: flex;
  align-items: center;
  gap: 12px;
  transition: background 0.1s, opacity 0.3s;
}
.job-card:last-child { border-bottom: none; }
.job-card:hover { background: var(--bg, #f8f9fa); }

.job-card--listing {
  padding: 10px 16px;
  align-items: center;
}
.job-card--hidden { opacity: 0.4; }
.job-card--hidden:hover { opacity: 1; }
.job-card--favorited { border-left: 3px solid var(--color-favorite, #d97706); }

.match-left-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-width: 80px;
}

.job-card-info { flex: 1; min-width: 0; }

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.title-row .title {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.title-row .actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* Meta row */
.meta-row {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  overflow: hidden;
  gap: 0.5rem;
  font-size: 11px;
  color: var(--text-secondary, #64748b);
  margin-top: 2px;
}
.meta-row > *:not(.job-listing-badge):not(.status-badge) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}
.meta-row > .job-listing-badge,
.meta-row > .status-badge {
  flex-shrink: 0;
}


/* Secondary link */
.link-secondary {
  color: var(--text-secondary, #64748b);
  text-decoration: none;
}
.link-secondary:hover { color: var(--primary, #2563eb); }

/* Match item tags */
.job-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
  align-items: center;
}

/* Skill tags */
.job-card-tags .skill-tag {
  display: inline-block;
  padding: 2px 8px;
  margin: 2px;
  background: var(--primary-08, rgba(37, 99, 235, 0.08));
  color: var(--primary, #2563eb);
  border-radius: 12px;
  font-size: 10px;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s;
}
.job-card-tags .skill-tag:hover { background: var(--primary-18, rgba(37, 99, 235, 0.18)); }

/* Rate badge in listing */
.job-card--listing .rate-badge { display: flex; flex-direction: column; align-items: center; gap: 0; line-height: 1.2; }
.job-card--listing .salary-source { font-size: 0.6rem; font-weight: 600; white-space: nowrap; }
.job-card--listing .salary-converted { font-size: 0.5rem; color: var(--color-text-secondary, #64748b); white-space: nowrap; }

/* AI analysis dot — compact indicator replacing full text badge */
.analysis-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-ai, #8b5cf6);
  vertical-align: middle;
  flex-shrink: 0;
  cursor: help;
}

</style>