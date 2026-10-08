<template>
  <div class="applications-view">
    <PageTitle title="Applications" :count="`${activeCount} active`" />

    <FilterPanel
      v-model="filters.searchQuery"
      placeholder="Search by title, company, or outcome..."
      :debounce-ms="150"
      show-search-icon
      :show-reset="true"
      :has-active-filters="hasActiveFilters"
      @reset="resetFilters"
    >
      <template #below>
        <FilterToggleGroup
          v-model="filters.currentStatus"
          :options="statusOptions"
          :multi="false"
        />
      </template>
      <template #actions>
        <BaseButton variant="outline" size="sm" @click="downloadCsv" :disabled="loading || !allApps.length">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          </template>
          Export CSV
        </BaseButton>
      </template>
    </FilterPanel>

    <SectionHeading title="Applications" :count="filteredApps.length || null" />

    <div class="applications-list">
      <DataTable
        :columns="appColumns"
        :rows="filteredApps"
        :loading="loading"
        :error="error"
        :row-class="appRowClass"
        empty-title="No matching applications"
        :empty-message="emptyStateMessage"
        :expandable="true"
        :expanded-rows="expandedSet"
        row-key="id"
        @toggle-expand="toggleExpand"
      >
        <template #cell-title="{ row }">
          <router-link :to="`/jobs/${row.job_external_id}`" class="link">
            {{ row.job_title || 'Untitled' }}
          </router-link>
        </template>
        <template #cell-company="{ row }">
          <span class="text-secondary">{{ row.company || '—' }}</span>
        </template>
        <template #cell-applied_at="{ row }">
          <span class="text-sm">{{ formatDate(row.applied_at) }}</span>
        </template>
        <template #cell-interview_at="{ row }">
          <span class="text-sm">{{ formatDate(row.interview_at) }}</span>
        </template>
        <template #cell-outcome="{ row }">
          <span class="text-sm">
            <span v-if="row.outcome_reason" :title="row.outcome || ''">{{ outcomeReasonLabel(row.outcome_reason) }}</span>
            <span v-else class="text-secondary">—</span>
          </span>
        </template>
        <template #cell-follow_up="{ row }">
          <span class="text-sm">
            <template v-if="row.follow_up_count > 0">
              {{ row.follow_up_count }} contact{{ row.follow_up_count !== 1 ? 's' : '' }}
            </template>
            <span v-else class="text-secondary">—</span>
          </span>
        </template>
        <template #cell-status="{ row }">
          <ApplicationStatusDropdown
            :status="row.status"
            :app-id="row.id"
            :transitions="getValidTransitions(row.status)"
            @transition="handleTransition"
            @reopen="handleReopen"
            @delete="handleDelete"
          />
        </template>

        <!-- Expanded row detail -->
        <template #expanded-row="{ row }">
          <div class="app-detail">
            <div class="detail-col detail-col--status">
              <section class="detail-section outcome-section">
                <h4 class="detail-heading">
                  <span class="heading-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/></svg></span>
                  Outcome
                </h4>
                <div class="outcome-row">
                  <span class="detail-badge" :class="outcomeBadgeClass(row)">{{ row.outcome_reason ? outcomeReasonLabel(row.outcome_reason) : 'Pending' }}</span>
                  <div class="detail-actions">
                    <BaseButton variant="primary" size="sm" @click="openOutcomeModal(row)">Record Outcome</BaseButton>
                    <BaseButton v-if="!isTerminal(row.status)" variant="outline" size="sm" @click="handleArchive(row)">Archive</BaseButton>
                  </div>
                </div>
                <div v-if="row.outcome" class="detail-field">
                  <span class="field-label">Notes:</span> {{ row.outcome }}
                </div>
              </section>

              <section class="detail-section">
                <h4 class="detail-heading">
                  <span class="heading-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg></span>
                  Interview Stages
                </h4>
                <div class="stages-track">
                  <label
                    class="stage-step"
                    v-for="(stage, si) in ['phone_screen', 'technical', 'onsite', 'offer']"
                    :key="stage"
                    :class="{ done: getInterviewStage(row, stage) }"
                  >
                    <input
                      type="checkbox"
                      class="stage-input"
                      :checked="getInterviewStage(row, stage)"
                      @change="toggleStage(row, stage)"
                    />
                    <span class="stage-dot">
                      <svg v-if="getInterviewStage(row, stage)" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                      <span v-else>{{ si + 1 }}</span>
                    </span>
                    <span class="stage-name">{{ stageLabel(stage) }}</span>
                  </label>
                </div>
              </section>

              <section class="detail-section">
                <h4 class="detail-heading">
                  <span class="heading-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg></span>
                  Follow-up Tracking
                </h4>
                <div class="follow-up-row">
                  <span class="field-label">Contacts:</span> {{ row.follow_up_count || 0 }}
                  <span v-if="row.last_contact_at" class="field-value">· Last: {{ formatDate(row.last_contact_at) }}</span>
                  <div class="follow-up-actions">
                    <BaseButton variant="outline" size="sm" @click="logFollowUp(row)">Log Follow-up</BaseButton>
                  </div>
                </div>
                <div v-if="row.follow_up_notes" class="detail-field">
                  <span class="field-label">Notes:</span> {{ row.follow_up_notes }}
                </div>
              </section>

              <section class="detail-section">
                <h4 class="detail-heading">Status History</h4>
                <BaseButton v-if="!statusLogs[row.id]" variant="outline" size="sm" @click="loadStatusLogs(row)">Show history</BaseButton>
                <ol v-else class="status-log">
                  <li v-for="log in statusLogs[row.id]" :key="log.id">
                    <span class="text-secondary">{{ formatDate(log.created_at) }}</span>
                    {{ log.from_status || 'created' }} → {{ log.to_status }}
                    <span v-if="log.reason" class="text-secondary">· {{ log.reason }}</span>
                  </li>
                  <li v-if="!statusLogs[row.id].length" class="text-secondary">No status changes recorded</li>
                </ol>
              </section>
            </div>

            <div class="detail-col detail-col--content">
              <section class="detail-section">
                <h4 class="detail-heading">
                  <span class="heading-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/></svg></span>
                  Interview Prep
                </h4>
                <div class="prep-tabs">
                  <button
                    v-for="s in prepStages"
                    :key="s.value"
                    class="prep-tab"
                    :class="{ active: prepActiveStage === s.value }"
                    @click="prepActiveStage = s.value"
                  >{{ s.label }}</button>
                </div>
                <div class="prep-actions">
                  <BaseButton variant="primary" size="sm" @click="generatePrep(row)" :disabled="prepLoading[row.id + '-' + prepActiveStage]">
                    {{ prepLoading[row.id + '-' + prepActiveStage] ? 'Generating...' : 'Generate Prep Pack' }}
                  </BaseButton>
                </div>
                <div v-if="row.id && prepData[row.id] && prepData[row.id][prepActiveStage]" class="prep-content">
                  <div class="prep-section">
                    <h5 class="prep-subheading">Likely Questions</h5>
                    <div v-for="(q, qi) in prepData[row.id][prepActiveStage].likely_questions" :key="qi" class="prep-question">
                      <p class="prep-q-text"><strong>{{ qi + 1 }}.</strong> {{ q.question }} <span class="prep-q-type">({{ q.type }})</span></p>
                      <p class="prep-tip">{{ q.prep_tip }}</p>
                      <div v-if="q.star" class="prep-star">
                        <span class="prep-star-label">STAR:</span>
                        <span>S: {{ q.star.situation }}</span>
                        <span>T: {{ q.star.task }}</span>
                        <span>A: {{ q.star.action }}</span>
                        <span>R: {{ q.star.result }}</span>
                      </div>
                    </div>
                  </div>
                  <div class="prep-section">
                    <h5 class="prep-subheading">STAR Mapping</h5>
                    <div v-for="(sm, si) in prepData[row.id][prepActiveStage].star_mapping" :key="si" class="prep-star-map">
                      <p><strong>{{ sm.category }}</strong>: {{ sm.story_angle }}</p>
                      <p class="prep-meta">Skill: {{ sm.relevant_skill }} | Experience: {{ sm.suggested_experience }}</p>
                    </div>
                  </div>
                  <div class="prep-section">
                    <h5 class="prep-subheading">Company Research</h5>
                    <p>{{ prepData[row.id][prepActiveStage].company_research?.brief }}</p>
                    <p v-if="prepData[row.id][prepActiveStage].company_research?.key_topics?.length" class="prep-meta">
                      Key topics: {{ prepData[row.id][prepActiveStage].company_research.key_topics.join(', ') }}
                    </p>
                  </div>
                </div>
              </section>

              <section class="detail-section">
                <h4 class="detail-heading">
                  <span class="heading-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg></span>
                  Documents
                </h4>
                <div class="doc-row">
                  <div class="doc-info">
                    <span class="doc-name">CV</span>
                  </div>
                  <div class="doc-actions">
                    <BaseButton variant="outline" size="sm" @click="generateCvPdf(row)" :disabled="generatingCV[row.id]">
                      {{ generatingCV[row.id] ? 'Generating...' : 'Generate PDF' }}
                    </BaseButton>
                    <a v-if="row.cvPdfUrl" :href="row.cvPdfUrl" target="_blank" class="download-link">Download</a>
                  </div>
                </div>

                <div class="doc-row" v-if="row.cover_letter">
                  <div class="doc-info">
                    <span class="doc-name">Cover Letter</span>
                    <p class="cl-preview">{{ row.cover_letter.substring(0, 220) }}<span v-if="row.cover_letter.length > 220">…</span></p>
                  </div>
                  <div class="doc-actions">
                    <BaseButton variant="outline" size="sm" @click="generateCoverLetterPdf(row)" :disabled="generatingCL[row.id]">
                      {{ generatingCL[row.id] ? 'Generating...' : 'Generate PDF' }}
                    </BaseButton>
                    <a v-if="row.coverLetterPdfUrl" :href="row.coverLetterPdfUrl" target="_blank" class="download-link">Download</a>
                  </div>
                </div>

                <div class="doc-row" v-if="row.archived_materials_path">
                  <div class="doc-info">
                    <span class="doc-name">Archived Materials</span>
                    <p class="doc-path">{{ row.archived_materials_path }}</p>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </template>
      </DataTable>
    </div>

    <!-- Outcome Recording Modal -->
    <BaseModal :visible="showOutcomeModal" title="Record Outcome" @close="cancelOutcome">
      <div class="outcome-form">
        <div class="form-group">
          <label>Outcome Reason</label>
          <select v-model="outcomeForm.outcome_reason" class="form-select">
            <option value="">Select reason...</option>
            <option value="hired">Hired</option>
            <option value="offer_declined">Offer Declined</option>
            <option value="rejected">Rejected</option>
            <option value="no_response">No Response</option>
            <option value="interview_only">Interview Only</option>
            <option value="skills_mismatch">Skills Mismatch</option>
            <option value="salary">Salary Expectations</option>
            <option value="culture">Culture Fit</option>
          </select>
        </div>
        <div class="form-group">
          <label>Notes (optional)</label>
          <textarea v-model="outcomeForm.outcome" class="form-textarea" rows="3" placeholder="Additional context..."></textarea>
        </div>
        <div class="form-actions">
          <BaseButton variant="outline" size="sm" @click="cancelOutcome">Cancel</BaseButton>
          <BaseButton variant="primary" size="sm" @click="saveOutcome" :disabled="!outcomeForm.outcome_reason">Save</BaseButton>
        </div>
      </div>
    </BaseModal>

    <!-- Confirm Follow-up Modal -->
    <BaseModal :visible="showFollowUpModal" title="Log Follow-up" @close="cancelFollowUp">
      <div class="follow-up-form">
        <p class="modal-note">Log a follow-up contact for <strong>{{ followUpApp?.job_title || 'this application' }}</strong>.</p>
        <div class="form-group">
          <label>Notes (optional)</label>
          <textarea v-model="followUpNotes" class="form-textarea" rows="3" placeholder="What was discussed?"></textarea>
        </div>
        <div class="form-actions">
          <BaseButton variant="outline" size="sm" @click="cancelFollowUp">Cancel</BaseButton>
          <BaseButton variant="primary" size="sm" @click="saveFollowUp">Log Contact</BaseButton>
        </div>
      </div>
    </BaseModal>

    <!-- Confirm Reopen Modal -->
    <ConfirmModal
      :visible="showReopenConfirm"
      title="Reopen Application"
      message='Reopen this application? It will be reset to "applied".'
      confirm-text="Reopen"
      confirm-variant="primary"
      @confirm="confirmReopen"
      @cancel="cancelReopen"
    />

    <!-- Confirm Delete Modal -->
    <ConfirmModal
      :visible="showDeleteConfirm"
      title="Delete Application"
      message="Delete this application permanently? This cannot be undone."
      confirm-text="Delete"
      confirm-variant="danger"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />

    <!-- Confirm Archive Modal -->
    <ConfirmModal
      :visible="showArchiveConfirm"
      title="Archive Application"
      message="Close this application and save its materials to the archive. Choose the final status:"
      confirm-text="Archive"
      confirm-variant="primary"
      @confirm="confirmArchive"
      @cancel="cancelArchive"
    >
      <template #message>
        <select v-model="archiveStatus" class="archive-status-select">
          <option v-for="s in archiveStatusOptions" :key="s" :value="s">{{ s }}</option>
        </select>
      </template>
    </ConfirmModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useFetch } from '../composables/useFetch'
import { showToast } from '../composables/useToast'
import { useFilters } from '../composables/useFilters'
import { useApplicationStatus } from '../composables/useApplicationStatus'
import { useRefreshOnScrapeComplete } from '../composables/useRefreshOnScrapeComplete'
import { useDateTime } from '../composables/useDateTime'
import DataTable from '../components/common/DataTable.vue'
import PageTitle from '../components/common/PageTitle.vue'
import FilterPanel from '../components/common/FilterPanel.vue'
import BaseButton from '../components/common/BaseButton.vue'
import BaseModal from '../components/common/BaseModal.vue'
import ApplicationStatusDropdown from '../components/applications/ApplicationStatusDropdown.vue'
import ConfirmModal from '../components/common/ConfirmModal.vue'
import FilterToggleGroup from '../components/common/filters/FilterToggleGroup.vue'

const { transitionApp, deleteApp, reopenApp, getValidTransitions, isTerminalStatus: isTerminal, updateApplication } = useApplicationStatus()
const { execute: fetchAppsApi } = useFetch('')
const route = useRoute()

const allApps = ref([])
const loading = ref(false)
const error = ref(null)

const { filters, hasActiveFilters, reset } = useFilters({
  searchQuery: '',
  currentStatus: '',
}, 'job_engine_applications_filters')

const jobIdFilter = ref(null)

// ── Expand/Collapse ──
const expandedSet = ref(new Set())

function toggleExpand(row) {
  const key = row.id
  const next = new Set(expandedSet.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  expandedSet.value = next
}

const statusOptions = computed(() => [
  { value: '', label: 'All', count: allApps.value.length },
  ...['applied', 'interview', 'offer', 'accepted', 'rejected', 'withdrawn'].map(s => ({
    value: s,
    label: s.charAt(0).toUpperCase() + s.slice(1),
    count: allApps.value.filter(a => a.status === s).length,
  })),
])

// ── Outcome Modal ──
const showOutcomeModal = ref(false)
const outcomeForm = ref({ outcome: '', outcome_reason: '' })
const outcomeApp = ref(null)

function openOutcomeModal(row) {
  outcomeApp.value = row
  outcomeForm.value = { outcome: row.outcome || '', outcome_reason: row.outcome_reason || '' }
  showOutcomeModal.value = true
}

async function saveOutcome() {
  if (!outcomeApp.value) return
  const appId = outcomeApp.value.id
  try {
    await updateApplication(appId, {
      outcome: outcomeForm.value.outcome,
      outcome_reason: outcomeForm.value.outcome_reason,
    })
    showToast('Outcome recorded', 'success')
    showOutcomeModal.value = false
    await fetchApps()
  } catch (e) {
    showToast(e.message || 'Failed to save outcome', 'error')
  }
}

function cancelOutcome() {
  showOutcomeModal.value = false
  outcomeApp.value = null
}

const OUTCOME_REASON_DANGER = new Set(['rejected', 'no_response', 'skills_mismatch', 'salary', 'culture'])

function outcomeBadgeClass(row) {
  const reason = row.outcome_reason
  if (!reason) return 'badge-pending'
  if (reason === 'hired') return 'badge-success'
  if (OUTCOME_REASON_DANGER.has(reason)) return 'badge-danger'
  return 'badge-warning' // offer_declined, interview_only
}

function outcomeReasonLabel(reason) {
  return reason.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

// ── Interview Stages ──
function getInterviewStage(row, stage) {
  try {
    const stages = typeof row.interview_stages === 'object' ? row.interview_stages : JSON.parse(row.interview_stages || '{}')
    return !!stages[stage]
  } catch { return false }
}

async function toggleStage(row, stage) {
  const stages = typeof row.interview_stages === 'object'
    ? { ...row.interview_stages }
    : JSON.parse(row.interview_stages || '{}')
  stages[stage] = !stages[stage]
  try {
    await updateApplication(row.id, { interview_stages: stages })
    await fetchApps()
  } catch (e) {
    showToast(e.message || 'Failed to update stage', 'error')
  }
}

function stageLabel(stage) {
  const labels = { phone_screen: 'Phone Screen', technical: 'Technical', onsite: 'Onsite', offer: 'Offer' }
  return labels[stage] || stage
}

// ── Follow-up ──
const showFollowUpModal = ref(false)
const followUpApp = ref(null)
const followUpNotes = ref('')

function logFollowUp(row) {
  followUpApp.value = row
  followUpNotes.value = ''
  showFollowUpModal.value = true
}

async function saveFollowUp() {
  if (!followUpApp.value) return
  const appId = followUpApp.value.id
  try {
    const res = await fetch(`/api/applications/${appId}/follow-up`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: followUpNotes.value || '' }),
    })
    if (!res.ok) throw new Error(`Follow-up failed: ${res.status}`)
    showToast('Follow-up logged', 'success')
    showFollowUpModal.value = false
    followUpApp.value = null
    await fetchApps()
  } catch (e) {
    showToast(e.message || 'Failed to log follow-up', 'error')
  }
}

function cancelFollowUp() {
  showFollowUpModal.value = false
  followUpApp.value = null
}

// ── Interview Prep ──
const prepStages = [
  { value: 'phone_screen', label: 'Phone Screen' },
  { value: 'technical', label: 'Technical' },
  { value: 'onsite', label: 'Onsite' },
  { value: 'final', label: 'Final' },
]
const prepActiveStage = ref('phone_screen')
const prepData = ref({})
const prepLoading = ref({})

async function generatePrep(row) {
  const key = row.id + '-' + prepActiveStage.value
  prepLoading.value = { ...prepLoading.value, [key]: true }
  try {
    const res = await fetch(`/api/applications/${row.id}/prep-pack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage: prepActiveStage.value }),
    })
    if (!res.ok) throw new Error(`Prep generation failed: ${res.status}`)
    const result = await res.json()
    prepData.value = {
      ...prepData.value,
      [row.id]: {
        ...(prepData.value[row.id] || {}),
        [prepActiveStage.value]: result.prep_pack,
      },
    }
    showToast('Prep pack generated', 'success')
  } catch (e) {
    showToast(e.message || 'Failed to generate prep pack', 'error')
  } finally {
    prepLoading.value = { ...prepLoading.value, [key]: false }
  }
}

// ── Archive ──

// ── CV / Cover Letter PDF Generation ──
const generatingCV = ref({})
const generatingCL = ref({})

async function generateCvPdf(row) {
  const id = row.id
  generatingCV.value = { ...generatingCV.value, [id]: true }
  try {
    const res = await fetch(`/api/applications/${id}/generate-cv`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `CV generation failed: ${res.status}`)
    }
    const result = await res.json()
    row.cvPdfUrl = `/api/applications/${id}/files/cv.pdf`
    row.cvLatexUrl = `/api/applications/${id}/files/cv.tex`
    showToast('CV PDF generated', 'success')
  } catch (e) {
    showToast(e.message || 'Failed to generate CV PDF', 'error')
  } finally {
    generatingCV.value = { ...generatingCV.value, [id]: false }
  }
}

async function generateCoverLetterPdf(row) {
  const id = row.id
  generatingCL.value = { ...generatingCL.value, [id]: true }
  try {
    const res = await fetch(`/api/applications/${id}/generate-cover-letter-pdf`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Cover letter PDF generation failed: ${res.status}`)
    }
    const result = await res.json()
    row.coverLetterPdfUrl = `/api/applications/${id}/files/cover_letter.pdf`
    row.coverLetterTexUrl = `/api/applications/${id}/files/cover_letter.tex`
    showToast('Cover Letter PDF generated', 'success')
  } catch (e) {
    showToast(e.message || 'Failed to generate cover letter PDF', 'error')
  } finally {
    generatingCL.value = { ...generatingCL.value, [id]: false }
  }
}

const showArchiveConfirm = ref(false)
const archiveApp = ref(null)
const archiveStatus = ref(null)
const archiveStatusOptions = computed(() =>
  archiveApp.value ? getValidTransitions(archiveApp.value.status).filter(isTerminal) : []
)

function handleArchive(row) {
  archiveApp.value = row
  archiveStatus.value = archiveStatusOptions.value[0]
  showArchiveConfirm.value = true
}

async function confirmArchive() {
  showArchiveConfirm.value = false
  const app = archiveApp.value
  archiveApp.value = null
  if (!app) return
  try {
    const res = await fetch(`/api/applications/${app.id}/archive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: archiveStatus.value }),
    })
    if (!res.ok) throw new Error(`Archive failed: ${res.status}`)
    showToast('Application archived', 'success')
    await fetchApps()
  } catch (e) {
    showToast(e.message || 'Failed to archive', 'error')
  }
}

// ── Status history ──
const statusLogs = ref({})

async function loadStatusLogs(row) {
  try {
    const res = await fetch(`/api/applications/${row.id}/logs`)
    if (!res.ok) throw new Error(`Failed to load history: ${res.status}`)
    statusLogs.value = { ...statusLogs.value, [row.id]: await res.json() }
  } catch (e) {
    showToast(e.message, 'error')
  }
}

function cancelArchive() {
  showArchiveConfirm.value = false
  archiveApp.value = null
}

// ── CSV Export ──
function downloadCsv() {
  const a = document.createElement('a')
  a.href = '/api/applications/export/csv'
  a.download = 'applications_export.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// Confirm modal state
const showReopenConfirm = ref(false)
const showDeleteConfirm = ref(false)
const pendingReopenId = ref(null)
const pendingDeleteApp = ref(null)

const activeCount = computed(() => {
  return allApps.value.filter(a => !isTerminal(a.status)).length
})

const filteredApps = computed(() => {
  let result = allApps.value
  if (filters.currentStatus) {
    result = result.filter(a => a.status === filters.currentStatus)
  }
  const q = filters.searchQuery.trim().toLowerCase()
  if (q) {
    result = result.filter(a => {
      const title = (a.job_title || '').toLowerCase()
      const company = (a.company || '').toLowerCase()
      const outcome = (a.outcome || '').toLowerCase()
      return title.includes(q) || company.includes(q) || outcome.includes(q)
    })
  }
  return result
})

const emptyStateMessage = computed(() => {
  if (filters.searchQuery.trim()) return 'Try a different search term'
  if (filters.currentStatus) return 'No applications with this status yet'
  return 'Track jobs you have applied to by clicking "Apply" on a job detail page'
})

const appColumns = [
  { key: 'title', label: 'Job' },
  { key: 'company', label: 'Company' },
  { key: 'applied_at', label: 'Applied' },
  { key: 'interview_at', label: 'Interview' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'follow_up', label: 'Follow-up' },
  { key: 'status', label: '', align: 'right' },
]

function appRowClass(row) {
  return isTerminal(row.status) ? 'app-row--closed' : ''
}

function resetFilters() {
  reset()
}

const { formatDate } = useDateTime()

async function handleTransition({ appId, newStatus }) {
  try {
    await transitionApp(appId, newStatus)
    await fetchApps()
  } catch (e) {
    showToast(e.message || 'Failed to transition', 'error')
  }
}

async function handleReopen(appId) {
  pendingReopenId.value = appId
  showReopenConfirm.value = true
}

async function confirmReopen() {
  showReopenConfirm.value = false
  const appId = pendingReopenId.value
  pendingReopenId.value = null
  if (!appId) return
  try {
    await reopenApp(appId)
    await fetchApps()
  } catch (e) {
    showToast(e.message || 'Failed to reopen', 'error')
  }
}

function cancelReopen() {
  showReopenConfirm.value = false
  pendingReopenId.value = null
}

async function handleDelete(app) {
  pendingDeleteApp.value = app
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  showDeleteConfirm.value = false
  const app = pendingDeleteApp.value
  pendingDeleteApp.value = null
  const appId = typeof app === 'object' ? app.id : app
  if (!appId) return
  try {
    await deleteApp(appId)
    await fetchApps()
  } catch (e) {
    showToast(e.message || 'Failed to delete', 'error')
  }
}

function cancelDelete() {
  showDeleteConfirm.value = false
  pendingDeleteApp.value = null
}

async function fetchApps() {
  loading.value = true; error.value = null
  try {
    let url = '/api/applications'
    if (jobIdFilter.value) url += '?job_id=' + jobIdFilter.value
    const result = await fetchAppsApi(url)
    allApps.value = result
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const jid = route.query.job_id ? parseInt(route.query.job_id, 10) : null
  if (jid) jobIdFilter.value = jid
  await fetchApps()
})

// Re-fetch when a scrape run adds/removes job applications
useRefreshOnScrapeComplete(() => fetchApps())
</script>

<style scoped>
.applications-list { margin-bottom: 24px; }
.link { color: var(--color-primary, #3b82f6); text-decoration: none; font-weight: 500; }
.link:hover { text-decoration: underline; }
.text-secondary { color: var(--color-text-secondary, #64748b); }
.text-sm { font-size: 0.78125rem; color: var(--color-text-secondary, #64748b); white-space: nowrap; font-variant-numeric: tabular-nums; }
.td-status { text-align: right; }


/* ── Expanded detail row ──
 * No card framing here — the table row itself already supplies the border,
 * so this is flush, flat content: a status sidebar (outcome/stages/
 * follow-up, tinted) beside a wider content pane (prep/documents). */
.app-detail {
  display: flex;
}

.detail-col { padding: 18px 20px; min-width: 0; }
.detail-col--status {
  flex: 0 0 300px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: var(--bg, #f8fafc);
  border-right: 1px solid var(--border, #e2e8f0);
}
.detail-col--content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
@media (max-width: 720px) {
  .app-detail { flex-direction: column; }
  .detail-col--status { flex: none; border-right: none; border-bottom: 1px solid var(--border, #e2e8f0); }
}

.detail-section { min-width: 0; }
.detail-heading {
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 10px;
  color: var(--text-secondary, #64748b);
  display: flex;
  align-items: center;
  gap: 6px;
}
.heading-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  background: var(--primary-08, rgba(37, 99, 235, .08));
  color: var(--primary, #2563eb);
  flex-shrink: 0;
}
.outcome-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}
.detail-badge {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
  text-transform: capitalize;
}
.badge-success { background: #dcfce7; color: #166534; }
.badge-danger { background: #fee2e2; color: #991b1b; }
.badge-warning { background: #fef3c7; color: #92400e; }
.badge-pending { background: #f1f5f9; color: #475569; }
.detail-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.detail-field {
  font-size: 0.8125rem;
  color: var(--text-secondary, #64748b);
  margin-top: 6px;
  line-height: 1.5;
}
.field-label { font-weight: 500; color: var(--text, #475569); }
.field-value { color: var(--text-secondary, #64748b); }

/* ── Interview stages stepper ── */
.stages-track {
  display: flex;
  align-items: flex-start;
}
.stage-step {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  text-align: center;
}
.stage-step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 10px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--border, #e2e8f0);
  z-index: 0;
}
.stage-step.done:not(:last-child)::after { background: var(--success, #16a34a); }
.stage-input {
  position: absolute;
  opacity: 0;
  width: 1px;
  height: 1px;
}
.stage-dot {
  position: relative;
  z-index: 1;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: 600;
  background: var(--surface, #fff);
  border: 2px solid var(--border, #cbd5e1);
  color: var(--text-secondary, #64748b);
  transition: all 0.15s;
}
.stage-step.done .stage-dot {
  background: var(--success, #16a34a);
  border-color: var(--success, #16a34a);
  color: #fff;
}
.stage-step:hover .stage-dot { border-color: var(--primary, #3b82f6); }
.stage-step:focus-within .stage-dot { box-shadow: var(--focus-ring, 0 0 0 3px rgba(37, 99, 235, .15)); }
.stage-name { font-size: 0.6875rem; color: var(--text, #334155); font-weight: 500; }
.stage-step.done .stage-name { color: var(--success, #16a34a); }

/* ── Follow-up ── */
.status-log {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.8125rem;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.archive-status-select {
  margin-top: 0.5rem;
  text-transform: capitalize;
}
.follow-up-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8125rem;
  flex-wrap: wrap;
}
.follow-up-actions { margin-left: auto; }

/* ── Interview Prep ── */
.prep-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
  flex-wrap: wrap;
  background: var(--bg, #f1f5f9);
  padding: 3px;
  border-radius: 7px;
  width: fit-content;
}
.prep-tab {
  padding: 4px 12px;
  font-size: 0.75rem;
  font-weight: 500;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary, #64748b);
  cursor: pointer;
  transition: all 0.15s;
}
.prep-tab:hover { color: var(--text, #1e293b); }
.prep-tab.active {
  background: var(--surface, #fff);
  color: var(--primary, #2563eb);
  box-shadow: var(--shadow, 0 1px 2px rgba(0, 0, 0, .08));
}
.prep-actions { margin-bottom: 10px; }
.prep-content {
  font-size: 0.8125rem;
  max-height: 400px;
  overflow-y: auto;
  padding-top: 12px;
  border-top: 1px solid var(--border, #e2e8f0);
}
.prep-section { margin-bottom: 14px; }
.prep-section:last-child { margin-bottom: 0; }
.prep-subheading {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin: 0 0 6px;
  color: var(--text-secondary, #64748b);
}
.prep-question { margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px dashed var(--border, #e2e8f0); }
.prep-question:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
.prep-q-text { margin: 0 0 2px; color: var(--text, #1e293b); }
.prep-q-type { color: var(--text-secondary, #64748b); font-size: 0.75rem; font-weight: 400; }
.prep-tip { margin: 0; color: var(--text-secondary, #64748b); font-size: 0.75rem; }
.prep-star {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-top: 4px;
  font-size: 0.75rem;
  color: var(--text-secondary, #64748b);
  background: var(--bg, #f8fafc);
  padding: 6px 8px;
  border-radius: 6px;
}
.prep-star-label { font-weight: 600; color: var(--text, #475569); }
.prep-star-map { margin-bottom: 6px; }
.prep-star-map p { margin: 0; }
.prep-meta { font-size: 0.75rem; color: var(--text-secondary, #64748b); }

/* ── Documents ── */
.doc-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--border, #e2e8f0);
}
.doc-row:first-of-type { border-top: none; padding-top: 0; }
.doc-info { min-width: 0; flex: 1; }
.doc-name { font-size: 0.8125rem; font-weight: 600; color: var(--text, #1e293b); }
.doc-path {
  margin: 4px 0 0;
  font-size: 0.75rem;
  color: var(--text-secondary, #64748b);
  font-family: ui-monospace, SFMono-Regular, monospace;
  word-break: break-all;
}
.cl-preview {
  margin: 4px 0 0;
  font-size: 0.78125rem;
  color: var(--text-secondary, #64748b);
  white-space: pre-wrap;
  max-height: 90px;
  overflow-y: auto;
  line-height: 1.5;
}
.doc-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── Outcome Modal ── */
.outcome-form, .follow-up-form {
  padding: 16px 0;
}
.form-group {
  margin-bottom: 14px;
}
.form-group label {
  display: block;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text, #334155);
  margin-bottom: 4px;
}
.form-select {
  width: 100%;
  padding: 8px 10px;
  font-size: 0.8125rem;
  border: 1px solid var(--border, #d1d5db);
  border-radius: 6px;
  background: var(--surface, #fff);
  color: var(--text, #1e293b);
}
.form-textarea {
  width: 100%;
  padding: 8px 10px;
  font-size: 0.8125rem;
  border: 1px solid var(--border, #d1d5db);
  border-radius: 6px;
  background: var(--surface, #fff);
  color: var(--text, #1e293b);
  resize: vertical;
  font-family: inherit;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.modal-note {
  font-size: 0.875rem;
  color: var(--text-secondary, #64748b);
  margin: 0 0 14px;
}
.download-link {
  font-size: 0.8125rem;
  color: var(--primary, #2563eb);
  text-decoration: underline;
  cursor: pointer;
  padding: 4px 8px;
}
.download-link:hover { color: #1d4ed8; }
.loading, .error { padding: 2rem; text-align: center; }
</style>
