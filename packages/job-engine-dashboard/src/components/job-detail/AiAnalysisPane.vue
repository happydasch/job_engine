<template>
  <div class="ai-box">
    <!-- Tab strip -->
    <AppTabs v-model="activeTab" :tabs="tabs" compact>
      <template #suffix>
        <span v-if="cached" class="ai-cached-dot" title="Loaded from cache" />
      </template>
    </AppTabs>

    <!-- Pill popover menu (teleported to body to avoid overflow: hidden clipping) -->
    <Teleport to="body">
      <div v-if="pillMenu" class="ai-popover" :style="{ position: 'fixed', left: pillMenu.x + 'px', top: pillMenu.y + 'px' }">
        <div class="ai-popover-title">Add "{{ pillMenu.item }}" to…</div>
        <button v-if="pillMenu.subKeys.length === 0"
          class="ai-popover-btn"
          :class="{ 'ai-popover-btn--exists': existsInProfile(pillMenu.item, pillMenu.section) }"
          @click="addToProfileAndClose(pillMenu.section, pillMenu.item)">
          <span class="ai-popover-icon"><AppIcon :name="existsInProfile(pillMenu.item, pillMenu.section) ? 'check' : 'plus'" :size="11" /></span>
          {{ pillMenu.section === 'career_goals' ? 'Career Goals' : 'Behavioral Keywords' }}
        </button>
        <button v-for="sub in pillMenu.subKeys" :key="sub"
          class="ai-popover-btn"
          :class="{ 'ai-popover-btn--exists': existsInProfile(pillMenu.item, pillMenu.section, sub) }"
          @click="addToProfileAndClose(pillMenu.section, pillMenu.item, sub)">
          <span class="ai-popover-icon"><AppIcon :name="existsInProfile(pillMenu.item, pillMenu.section, sub) ? 'check' : 'plus'" :size="11" /></span>
          {{ sub }}
        </button>
        <div class="ai-popover-divider"></div>
        <button class="ai-popover-btn ai-popover-btn--search" @click="searchJobs(pillMenu.item, pillMenu.searchParam)">
          Search Jobs
        </button>
      </div>
    </Teleport>

    <!-- Loading skeleton -->
    <div v-if="busy" class="ai-body">
      <div class="skel-line" />
      <div class="skel-row">
        <span class="skel-pill" />
        <span class="skel-pill" />
        <span class="skel-pill" />
      </div>
      <div class="skel-line skel--short skel--last" />
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="ai-body ai-body--center">
      <p class="ai-err-msg">{{ error }}</p>
      <BaseButton variant="secondary" @click="loadCurrentTab">Retry</BaseButton>
    </div>

    <!-- ====== ANALYSIS TAB ====== -->
    <div v-else-if="activeTab === 'analysis'" class="ai-body">
      <div v-if="!analysis" class="ai-empty">
        <p>Analyze this job - skills, culture, red flags and more.</p>
        <BaseButton variant="primary" @click="loadAnalysis" :disabled="busy || parentBusy" :loading="busy">Analyze with AI</BaseButton>
      </div>
      <template v-else>
        <p v-if="analysis.summary" class="ai-summary">{{ analysis.summary }}</p>

        <div v-if="analysis.relevance_notes" class="ai-b">
          <h4 class="ai-h">Relevance</h4>
          <p class="ai-t">{{ analysis.relevance_notes }}</p>
        </div>

        <div v-if="analysis.seniority" class="ai-b">
          <h4 class="ai-h">Seniority</h4>
          <span class="ai-pill ai-pill--green">{{ analysis.seniority }}</span>
        </div>

        <div v-if="analysis.key_skills?.length" class="ai-b">
          <h4 class="ai-h">Required Skills</h4>
          <div class="ai-pills">
            <span v-for="s in analysis.key_skills" :key="s"
              class="ai-pill ai-pill--blue clickable-pill"
              @click="showPillMenu($event, 'skills', s)">{{ s }}</span>
          </div>
        </div>

        <div v-if="analysis.nice_to_have?.length" class="ai-b">
          <h4 class="ai-h">Nice to Have</h4>
          <div class="ai-pills">
            <span v-for="s in analysis.nice_to_have" :key="s"
              class="ai-pill ai-pill--amber clickable-pill"
              @click="showPillMenu($event, 'skills', s)">{{ s }}</span>
          </div>
        </div>

        <div v-if="analysis.skills_inferred?.length" class="ai-b">
          <h4 class="ai-h">Inferred Skills</h4>
          <div class="ai-pills">
            <span v-for="s in analysis.skills_inferred" :key="s"
              class="ai-pill ai-pill--purple clickable-pill"
              @click="showPillMenu($event, 'skills', s)">{{ s }}</span>
          </div>
        </div>

        <div v-if="analysis.career_goals?.length" class="ai-b">
          <h4 class="ai-h">Career Goals</h4>
          <div class="ai-pills">
            <span v-for="g in analysis.career_goals" :key="g"
              class="ai-pill ai-pill--teal clickable-pill"
              @click="showPillMenu($event, 'career_goals', g)">{{ g }}</span>
          </div>
        </div>

        <div v-if="analysis.behavioral_keywords?.length" class="ai-b">
          <h4 class="ai-h">Behavioral Keywords</h4>
          <div class="ai-pills">
            <span v-for="k in analysis.behavioral_keywords" :key="k"
              class="ai-pill ai-pill--orange clickable-pill"
              @click="showPillMenu($event, 'behavioral_keywords', k)">{{ k }}</span>
          </div>
        </div>

        <div v-if="analysis.responsibilities?.length" class="ai-b">
          <h4 class="ai-h">Responsibilities</h4>
          <ul class="ai-list">
            <li v-for="(r, i) in analysis.responsibilities" :key="i">{{ r }}</li>
          </ul>
        </div>

        <div v-if="analysis.red_flags?.length" class="ai-b">
          <h4 class="ai-h">Red Flags</h4>
          <div class="ai-red-wrap">
            <div v-for="(f, i) in analysis.red_flags" :key="i" class="ai-red">{{ f }}</div>
          </div>
        </div>
      </template>
    </div>

    <!-- ====== MATCH TAB ====== -->
    <div v-else-if="activeTab === 'explain'" class="ai-body">
      <div v-if="!explain" class="ai-empty">
        <p>Understand how this job matches your profile.</p>
        <BaseButton variant="primary" @click="loadExplain" :disabled="busy || parentBusy" :loading="busy">Explain Match</BaseButton>
      </div>
      <template v-else>
        <div v-if="explain.recommendation" class="ai-b">
          <h4 class="ai-h">Recommendation</h4>
          <span class="ai-rec" :class="'ai-rec--' + explain.recommendation">{{ recLabel(explain.recommendation) }}</span>
        </div>

        <p v-if="explain.summary" class="ai-summary">{{ explain.summary }}</p>

        <div v-if="explain.strengths?.length" class="ai-b">
          <h4 class="ai-h">Strengths</h4>
          <ul class="ai-list">
            <li v-for="(s, i) in explain.strengths" :key="i">{{ s }}</li>
          </ul>
        </div>

        <div v-if="explain.gaps?.length" class="ai-b">
          <h4 class="ai-h">Gaps</h4>
          <ul class="ai-list">
            <li v-for="(g, i) in explain.gaps" :key="i">{{ g }}</li>
          </ul>
        </div>
      </template>
    </div>

    <!-- ====== LETTER TAB (Application Letter) ====== -->
    <div v-else-if="activeTab === 'letter'" class="ai-body ai-letter-layout">
      <div class="ai-letter-grid">
        <!-- LEFT COLUMN: Config -->
        <div class="ai-letter-config">
          <p class="ai-letter-desc">Create a tailored application letter from scratch. Adjust the settings below to match your needs.</p>

          <!-- Editable draft from analysis -->
          <details v-if="letterDraft" class="ai-letter-draft-box" :open="draftOpen" @toggle="draftOpen = $event.target.open">
            <summary>Draft from analysis (used as reference)</summary>
            <textarea v-model="letterDraft" class="ai-letter-draft-textarea" rows="6" placeholder="Edit the draft or leave as-is..."></textarea>
            <div class="ai-letter-draft-actions">
              <BaseButton v-if="letterDraft !== originalDraft" variant="link" size="sm" @click="resetDraft">Reset to original</BaseButton>
            </div>
          </details>

          <div class="ai-letter-field">
            <label class="ai-letter-label">Style</label>
            <div class="ai-letter-options">
              <button v-for="opt in styleOptions" :key="opt.value"
                class="ai-letter-opt"
                :class="{ 'is-active': letterSettings.style === opt.value }"
                @click="letterSettings.style = opt.value"
              >{{ opt.label }}</button>
            </div>
          </div>

          <div class="ai-letter-field">
            <label class="ai-letter-label">Tone</label>
            <div class="ai-letter-options">
              <button v-for="opt in toneOptions" :key="opt.value"
                class="ai-letter-opt"
                :class="{ 'is-active': letterSettings.tone === opt.value }"
                @click="letterSettings.tone = opt.value"
              >{{ opt.label }}</button>
            </div>
          </div>

          <div class="ai-letter-field">
            <label class="ai-letter-label">Length</label>
            <div class="ai-letter-options">
              <button v-for="opt in lengthOptions" :key="opt.value"
                class="ai-letter-opt"
                :class="{ 'is-active': letterSettings.length === opt.value }"
                @click="letterSettings.length = opt.value"
              >{{ opt.label }}</button>
            </div>
          </div>

          <div class="ai-letter-field">
            <label class="ai-letter-label">Language</label>
            <select v-model="letterSettings.language">
              <option value="english">English</option>
              <option value="polish">Polish</option>
              <option value="german">German</option>
              <option value="french">French</option>
              <option value="spanish">Spanish</option>
              <option value="ukrainian">Ukrainian</option>
            </select>
          </div>

          <div class="ai-letter-field">
            <label class="ai-letter-review">
              <input type="checkbox" v-model="letterSettings.review" />
              Review pass (second LLM call checks for hallucinations)
            </label>
          </div>
        </div>

        <!-- RIGHT COLUMN: Generated letter -->
        <div class="ai-letter-output">
          <template v-if="letter">
            <div class="ai-letter-bar">
              <span class="ai-letter-words">{{ letterWordCount }} words</span>
              <div class="ai-letter-actions">
                <span class="ai-letter-lang-badge">{{ letterResultLanguage }}</span>
                <BaseButton variant="secondary" size="sm" @click="copyLetter">{{ copied ? 'Copied' : 'Copy' }}</BaseButton>
              </div>
            </div>
            <div class="ai-letter" :class="{ 'ai-letter--stale': generatingLetter }">{{ letter }}</div>
          </template>
          <div v-else class="ai-letter-empty">
            <p>Configure the settings on the left and click Generate to create your cover letter.</p>
          </div>
        </div>
      </div>

      <!-- Generate button — full width below the grid -->
      <div class="ai-letter-actions-bottom">
        <BaseButton variant="primary" @click="generateApplicationLetter" :disabled="generatingLetter" :loading="generatingLetter">
          {{ letter ? 'Regenerate' : 'Generate Application Letter' }}
        </BaseButton>
      </div>

      <!-- PDF export — same CV/cover-letter pipeline as the Applications page -->
      <div class="ai-letter-pdf-section">
        <p v-if="!props.applicationId" class="ai-letter-pdf-hint">
          Apply to this job to generate a CV or cover letter PDF.
        </p>
        <template v-else>
          <div class="ai-letter-pdf-row">
            <BaseButton variant="outline" size="sm" @click="generateCvPdf" :disabled="generatingCV">
              {{ generatingCV ? 'Generating...' : 'Generate CV PDF' }}
            </BaseButton>
            <a v-if="cvPdfUrl" :href="cvPdfUrl" target="_blank" class="download-link">Download PDF</a>
          </div>
          <div class="ai-letter-pdf-row">
            <BaseButton variant="outline" size="sm" @click="generateLetterPdf" :disabled="generatingCL || !letter">
              {{ generatingCL ? 'Generating...' : 'Save Letter & Generate PDF' }}
            </BaseButton>
            <a v-if="coverLetterPdfUrl" :href="coverLetterPdfUrl" target="_blank" class="download-link">Download PDF</a>
          </div>
          <p v-if="!letter" class="ai-letter-pdf-hint">Generate an application letter above first.</p>
        </template>
      </div>
    </div>

    <!-- ====== Q&A TAB ====== -->
    <div v-else-if="activeTab === 'questions'" class="ai-body">
      <div v-if="!questions" class="ai-empty">
        <p>Prepare with AI-generated interview questions.</p>
        <BaseButton variant="primary" @click="loadQuestions" :disabled="busy || parentBusy" :loading="busy">Suggest Questions</BaseButton>
      </div>
      <template v-else>

        <div v-for="(q, i) in questions" :key="i" class="ai-qa-card">
          <div class="ai-qa-head">
            <span class="ai-qa-num">{{ i + 1 }}</span>
            <span v-if="q.type" class="ai-qa-type-badge" :class="'ai-qa-type--' + q.type">{{ q.type.replace('_', ' ') }}</span>
            <div class="ai-qa-question">{{ q.question }}</div>
          </div>
          <p v-if="q.prep_tip" class="ai-qa-tip">{{ q.prep_tip }}</p>
          <!-- STAR (behavioral only) -->
          <div v-if="starObj(q)" class="ai-qa-star">
            <div class="ai-qa-star-row">
              <span class="ai-qa-star-label">S</span>
              <span class="ai-qa-star-text">{{ starObj(q).situation }}</span>
            </div>
            <div class="ai-qa-star-row">
              <span class="ai-qa-star-label">T</span>
              <span class="ai-qa-star-text">{{ starObj(q).task }}</span>
            </div>
            <div class="ai-qa-star-row">
              <span class="ai-qa-star-label">A</span>
              <span class="ai-qa-star-text">{{ starObj(q).action }}</span>
            </div>
            <div class="ai-qa-star-row">
              <span class="ai-qa-star-label">R</span>
              <span class="ai-qa-star-text">{{ starObj(q).result }}</span>
            </div>
          </div>
          <div v-else-if="q.star_context" class="ai-qa-star">
            <div class="ai-qa-star-fallback">{{ q.star_context }}</div>
          </div>
        </div>

        <div class="ai-qa-actions">
          <BaseButton variant="primary" class="ai-qa-copy-all" @click="copyAllQuestions">
            {{ copiedAll ? 'Copied!' : 'Copy All' }}
          </BaseButton>
        </div>

      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useFetch } from '../../composables/useFetch'
import { showToast } from '../../composables/useToast'
import { useTaskPoll } from '../../composables/useTaskPoll'
import { useAddToProfile } from '../../composables/useAddToProfile'
import AppIcon from '../common/AppIcon.vue'
import AppTabs from '../common/AppTabs.vue'
import BaseButton from '../common/BaseButton.vue'

const router = useRouter()

const props = defineProps({
  jobId: { type: String, required: true },
  applicationId: { type: [Number, String], default: null },
  parentBusy: { type: Boolean, default: false },
})
const emit = defineEmits(['busy-change', 'refresh'])

const tabs = [
  { key: 'analysis', label: 'Analysis' },
  { key: 'explain', label: 'Match' },
  { key: 'letter', label: 'Letter' },
  { key: 'questions', label: 'Q&A' },
]
const activeTab = ref('analysis')
const analysis = ref(null)
const explain = ref(null)
const letter = ref(null)
const letterDraft = ref(null)
const originalDraft = ref(null)
const draftOpen = ref(false)
const questions = ref(null)
const busy = ref(false)
const error = ref(null)
const cached = ref(false)
const copied = ref(false)
const generatingLetter = ref(false)
const letterResultLanguage = ref('')
const generatingCV = ref(false)
const generatingCL = ref(false)
const cvPdfUrl = ref(null)
const coverLetterPdfUrl = ref(null)

// Background LLM letter task — polled via shared useTaskPoll
const letterTaskId = ref(null)
const { status: letterTaskStatus, result: letterTaskResult, error: letterTaskError, stop: stopLetterPoll } = useTaskPoll(letterTaskId)
let letterTimeout = null

watch(letterTaskStatus, (st) => {
  if (st === 'completed') {
    clearTimeout(letterTimeout)
    const r = letterTaskResult.value
    if (r?.letter) {
      letter.value = r.letter
      letterResultLanguage.value = r.language || letterSettings.value.language
    } else {
      error.value = 'Failed to generate application letter'
    }
    generatingLetter.value = false
  } else if (st === 'failed') {
    clearTimeout(letterTimeout)
    error.value = letterTaskError.value || 'LLM analysis failed'
    generatingLetter.value = false
  }
})

const styleOptions = [
  { value: 'professional', label: 'Professional' },
  { value: 'concise', label: 'Concise' },
  { value: 'detailed', label: 'Detailed' },
  { value: 'enthusiastic', label: 'Enthusiastic' },
]
const toneOptions = [
  { value: 'formal', label: 'Formal' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'warm', label: 'Warm' },
  { value: 'confident', label: 'Confident' },
]
const lengthOptions = [
  { value: 'short', label: 'Short' },
  { value: 'medium', label: 'Medium' },
  { value: 'long', label: 'Long' },
]
const letterSettings = ref({
  language: 'english',
  style: 'professional',
  tone: 'neutral',
  length: 'medium',
  review: false,
})

const letterWordCount = computed(() => {
  if (!letter.value) return 0
  return letter.value.trim().split(/\s+/).length
})

// ── Pill popover ──
const pillMenu = ref(null) // { x, y, section, item, subKeys, searchParam } or null
const { skillCategories, loadProfileData, existsInProfile, addToProfile } = useAddToProfile()

function showPillMenu(event, section, item) {
  const rect = event.currentTarget.getBoundingClientRect()
  let subKeys = []
  let searchParam = 'skill'
  if (section === 'skills') {
    subKeys = skillCategories.value
    searchParam = 'skill'
  } else if (section === 'career_goals') {
    subKeys = []  // Flat list — no sub-categories
    searchParam = 'q'
  } else if (section === 'behavioral_keywords') {
    subKeys = []  // Flat list — no sub-categories
    searchParam = 'q'
  }
  pillMenu.value = {
    x: rect.left,
    y: rect.bottom + 4,
    section,
    item,
    subKeys,
    searchParam,
  }
}

function closePillMenu() {
  pillMenu.value = null
}

function onDocumentClick(event) {
  if (!pillMenu.value) return
  // Don't close when clicking on a pill (it will re-open)
  if (event.target.closest('.clickable-pill')) return
  const popover = document.querySelector('.ai-popover')
  if (popover && !popover.contains(event.target)) {
    closePillMenu()
  }
}

async function addToProfileAndClose(section, item, subKey = null) {
  closePillMenu()
  await addToProfile(section, item, subKey)
}

function searchJobs(item, param = 'skill') {
  closePillMenu()
  router.push('/jobs?' + param + '=' + encodeURIComponent(item))
}

// ── Q&A helpers ──
const copiedAll = ref(false)

function copyAllQuestions() {
  if (!questions.value) return
  const text = questions.value
    .map((q, i) => `Q${i + 1}: ${q.question}\n\n${q.prep_tip ? `Tip: ${q.prep_tip}\n\n` : ''}${q.type ? `Type: ${q.type.replace('_', ' ')}` : ''}`)
    .join('\n\n---\n\n')
  navigator.clipboard.writeText(text).then(() => {
    copiedAll.value = true
    setTimeout(() => { copiedAll.value = false }, 2000)
  }).catch(() => {})
}

function starObj(q) {
  // New structured format
  if (q.star && typeof q.star === 'object' && q.star.situation) {
    return q.star
  }
  // Backward-compatible fallback: return null so old star_context renders as text
  return null
}

function recLabel(r) {
  return ({ strong_match: 'Strong Match', good_match: 'Good Match', possible: 'Possible', weak_match: 'Weak Match' })[r] || r
}

function loadCurrentTab() {
  const m = { analysis: loadAnalysis, explain: loadExplain, letter: loadLetter, questions: loadQuestions }
  m[activeTab.value]()
}

function loadAnalysis() { busy.value = true; emit('refresh') }
function loadExplain() { busy.value = true; emit('refresh') }
function loadLetter() {
  if (letter.value) return
  // Show settings panel — user clicks generate manually
}
function loadQuestions() { busy.value = true; emit('refresh') }

async function generateApplicationLetter() {
  generatingLetter.value = true; error.value = null
  try {
    const res = await fetch('/api/tasks/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: props.jobId,
        task_type: 'llm_application_letter',
        language: letterSettings.value.language,
        style: letterSettings.value.style,
        tone: letterSettings.value.tone,
        length: letterSettings.value.length,
        draft: letterDraft.value || undefined,
        review: letterSettings.value.review,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const { task_id } = await res.json()

    // Hand polling over to the useTaskPoll watcher below (with a client-side
    // timeout — the task keeps running server-side so the letter is still cached)
    letterTimeout = setTimeout(() => {
      stopLetterPoll()
      if (!letter.value) error.value = 'Application letter generation timed out'
      generatingLetter.value = false
    }, 180000) // 3 min timeout
    letterTaskId.value = task_id
  } catch (e) {
    error.value = e.message
    generatingLetter.value = false
  }
}

async function generateCvPdf() {
  if (!props.applicationId) return
  generatingCV.value = true
  try {
    const res = await fetch(`/api/applications/${props.applicationId}/generate-cv`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    cvPdfUrl.value = `/api/applications/${props.applicationId}/files/cv.pdf`
  } catch (e) {
    showToast(e.message || 'Failed to generate CV PDF', 'error')
  } finally {
    generatingCV.value = false
  }
}

async function generateLetterPdf() {
  if (!props.applicationId || !letter.value) return
  generatingCL.value = true
  try {
    // Save the currently generated letter onto the application first — the
    // PDF pipeline (same one the Applications page uses) reads it from there.
    const patchRes = await fetch(`/api/applications/${props.applicationId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cover_letter: letter.value }),
    })
    if (!patchRes.ok) {
      const err = await patchRes.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${patchRes.status}`)
    }
    const res = await fetch(`/api/applications/${props.applicationId}/generate-cover-letter-pdf`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    coverLetterPdfUrl.value = `/api/applications/${props.applicationId}/files/cover_letter.pdf`
  } catch (e) {
    showToast(e.message || 'Failed to generate cover letter PDF', 'error')
  } finally {
    generatingCL.value = false
  }
}

async function copyLetter() {
  if (!letter.value) return
  try {
    await navigator.clipboard.writeText(letter.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch { copied.value = false }
}

function resetDraft() {
  letterDraft.value = originalDraft.value
}
async function loadCachedData() {
  try {
    const { execute } = useFetch(`/api/jobs/${props.jobId}/analysis`)
    const result = await execute()
    if (result?.status === 'ok') {
      let found = false
      if (result.analysis) { analysis.value = result.analysis; found = true }
      if (result.explain_match) { explain.value = result.explain_match; found = true }
      if (result.cover_letter) {
        letterDraft.value = result.cover_letter
        originalDraft.value = result.cover_letter
        found = true
      }
      if (result.questions) { questions.value = result.questions; found = true }
      if (found) cached.value = true
      return found
    }
    return false
  } catch {
    // No cached data available — not an error, user can click to generate
    return false
  }
}

async function loadLanguageSetting() {
  try {
    const { execute } = useFetch('/api/app-settings')
    const result = await execute()
    if (result?.language) {
      letterSettings.value.language = result.language
    }
  } catch {
    // Fall back to default 'english'
  }
}

onMounted(() => {
  loadLanguageSetting()
  loadCachedData()
  loadProfileData()
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  clearTimeout(letterTimeout)
  document.removeEventListener('click', onDocumentClick)
})</script>

<style scoped>
/* ── Card shell ── */
.ai-box {
  position: relative;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02);
}

/* ── Tab strip (AppTabs compact variant) — cached dot position ── */
.ai-cached-dot {
  position: absolute;
  top: 0.375rem;
  right: 0.5rem;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success, #16a34a);
}

/* ── Body ── */
.ai-body { padding: 1rem; }
.ai-body--center { text-align: center; padding: 2rem 1rem; }

/* ── Skeleton ── */
.skel-line {
  height: 10px;
  margin-bottom: 0.75rem;
  width: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skel--short { width: 55%; }
.skel--last { margin-bottom: 0; }
.skel-row { display: flex; gap: 6px; margin-bottom: 0.75rem; }
.skel-pill {
  display: inline-block;
  height: 20px;
  width: 52px;
  border-radius: 10px;
  background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* ── Error ── */
.ai-err-msg { font-size: 0.8125rem; color: var(--color-text-secondary, #64748b); margin-bottom: 0.75rem; }

/* ── Empty state ── */
.ai-empty { text-align: center; padding: 2rem 0.5rem; }
.ai-empty p { font-size: 0.8125rem; color: var(--color-text-secondary, #64748b); margin-bottom: 0.75rem; line-height: 1.5; }

/* Buttons come from the global button system (buttons.css) via BaseButton. */

/* ── Section block ── */
.ai-b { margin-bottom: 1rem; }
.ai-b:last-child { margin-bottom: 0; }

/* ── Section heading ── */
.ai-h {
  margin: 0 0 0.375rem;
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-text-secondary, #64748b);
}

/* ── Summary text ── */
.ai-summary {
  font-size: 0.8125rem;
  line-height: 1.6;
  margin-bottom: 1rem;
  color: var(--color-text, #1e293b);
}
.ai-t { font-size: 0.8125rem; line-height: 1.6; margin: 0; }

/* ── Pill / tag system ── */
.ai-pills { display: flex; flex-wrap: wrap; gap: 4px; }
.ai-pill {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.5;
}
.ai-pill--blue   { background: var(--color-primary-08, rgba(37, 99, 235, 0.08)); color: var(--color-primary, #2563eb); }
.ai-pill--amber  { background: var(--color-profile-boosted-bg, rgba(245, 158, 11, 0.12)); color: var(--color-profile-boosted, #b45309); }
.ai-pill--purple { background: rgba(99, 102, 241, 0.08); color: #4338ca; }
.ai-pill--green  { background: var(--color-profile-behavioral-bg, rgba(22, 163, 74, 0.08)); color: var(--color-profile-behavioral, #16a34a); font-weight: 600; }
.ai-pill--teal { background: var(--color-profile-goal-bg, rgba(139, 92, 246, 0.08)); color: var(--color-profile-goal, #7c3aed); }
.ai-pill--orange { background: var(--color-profile-behavioral-bg, rgba(22, 163, 74, 0.08)); color: var(--color-profile-behavioral, #16a34a); }

.clickable-pill {
  cursor: pointer;
  transition: filter 0.12s, transform 0.12s;
}
.clickable-pill:hover {
  filter: brightness(0.9);
  transform: translateY(-1px);
}

/* ── Pill popover menu ── */
.ai-popover {
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
.ai-popover-title {
  padding: 8px 12px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary, #64748b);
  border-bottom: 1px solid var(--color-border, #e2e8f0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-popover-btn {
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
.ai-popover-btn:hover {
  background: var(--color-bg-subtle, #f1f5f9);
}
.ai-popover-btn--exists {
  color: var(--color-success, #16a34a);
  font-weight: 600;
}
.ai-popover-btn--search {
  color: var(--color-primary, #3b82f6);
}
.ai-popover-divider {
  height: 1px;
  background: var(--color-border, #e2e8f0);
  margin: 0;
}
.ai-popover-icon {
  font-size: 0.75rem;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

/* ── Bullet list ── */
.ai-list { margin: 0; padding-left: 1.25rem; font-size: 0.8125rem; line-height: 1.7; }
.ai-list li { margin-bottom: 1px; }

/* ── Red flags ── */
.ai-red-wrap { display: flex; flex-direction: column; gap: 3px; }
.ai-red {
  font-size: 0.8125rem;
  color: #dc2626;
  padding: 4px 8px;
  background: #fef2f2;
  border-radius: 4px;
}

/* ── Recommendation pill ── */
.ai-rec {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 600;
}
.ai-rec--strong_match { background: #dcfce7; color: #166534; }
.ai-rec--good_match   { background: rgba(59, 130, 246, 0.08); color: #1d4ed8; }
.ai-rec--possible     { background: #fef9c3; color: #854d0e; }
.ai-rec--weak_match   { background: #fef2f2; color: #991b1b; }

/* ── Cover letter / Application letter ── */
.ai-letter-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
.ai-letter-words { font-size: 0.75rem; color: var(--color-text-secondary, #64748b); }
.ai-letter-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.ai-letter-lang-badge {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-primary, #3b82f6);
  background: rgba(59, 130, 246, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

/* ── Letter settings panel ── */
.ai-letter-settings {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.ai-letter-desc {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--color-text-secondary, #64748b);
  margin: 0;
}
.ai-letter-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.ai-letter-field select {
  width: 100%;
  padding: 0.5rem 0.625rem;
  font-family: inherit;
  font-size: 0.8125rem;
  color: var(--color-text, #1e293b);
  background: var(--color-bg, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.12s;
  appearance: auto;
}
.ai-letter-field select:hover {
  border-color: var(--color-primary, #3b82f6);
}
.ai-letter-field select:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
}

/* ── Letter draft box ── */
.ai-letter-draft-box {
  font-size: 0.75rem;
  border: 1px dashed var(--color-border, #e2e8f0);
  border-radius: 6px;
  padding: 0.5rem 0.625rem;
  background: var(--color-bg-subtle, #fafafa);
}
.ai-letter-draft-box summary {
  cursor: pointer;
  color: var(--color-text-secondary, #64748b);
  font-weight: 500;
  user-select: none;
}
.ai-letter-draft-box summary:hover {
  color: var(--color-primary, #3b82f6);
}
.ai-letter-draft-textarea {
  margin-top: 0.5rem;
  width: 100%;
  font-family: inherit;
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--color-text, #1e293b);
  padding: 0.5rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 4px;
  background: var(--color-bg, #fff);
  resize: vertical;
  min-height: 100px;
}
.ai-letter-draft-textarea:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
}
.ai-letter-draft-actions {
  margin-top: 0.25rem;
  display: flex;
  justify-content: flex-end;
}
.ai-letter-label {
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-text-secondary, #64748b);
}
.ai-letter-review {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #64748b);
  cursor: pointer;
}
.ai-letter-options {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.ai-letter-opt {
  padding: 4px 12px;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
  background: var(--color-bg, #fff);
  font-family: inherit;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-secondary, #64748b);
  cursor: pointer;
  transition: all 0.12s;
}
.ai-letter-opt:hover {
  border-color: var(--color-primary, #3b82f6);
  color: var(--color-primary, #3b82f6);
}
.ai-letter-opt.is-active {
  border-color: var(--color-primary, #3b82f6);
  background: rgba(59, 130, 246, 0.08);
  color: var(--color-primary, #3b82f6);
  font-weight: 600;
}

/* ── Letter layout — settings + letter always visible ── */
.ai-letter-layout {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.ai-letter--stale {
  opacity: 0.5;
  transition: opacity 0.2s;
}
.ai-letter {
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 0.8125rem;
  line-height: 1.75;
  color: var(--color-text, #1e293b);
}

/* ── Letter two-column grid ── */
.ai-letter-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}
.ai-letter-config {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.ai-letter-output {
  display: flex;
  flex-direction: column;
  min-height: 200px;
}
.ai-letter-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  border: 1px dashed var(--color-border, #e2e8f0);
  border-radius: 8px;
  background: var(--color-bg-subtle, #fafafa);
  padding: 2rem 1rem;
  text-align: center;
}
.ai-letter-empty p {
  font-size: 0.8125rem;
  color: var(--color-text-secondary, #64748b);
  line-height: 1.5;
  margin: 0;
  max-width: 22em;
}
.ai-letter-actions-bottom {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.25rem;
}
.ai-letter-pdf-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 0.75rem;
  margin-top: 0.5rem;
  border-top: 1px solid var(--border, #e2e8f0);
}
.ai-letter-pdf-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ai-letter-pdf-hint {
  font-size: 0.8125rem;
  color: var(--text-secondary, #64748b);
  margin: 0;
}
.download-link {
  font-size: 0.8125rem;
  color: var(--primary, #2563eb);
  text-decoration: underline;
  cursor: pointer;
  padding: 4px 8px;
}
.download-link:hover { color: #1d4ed8; }

/* ── Responsive: single column on narrow screens ── */
@media (max-width: 640px) {
  .ai-letter-grid {
    grid-template-columns: 1fr;
  }
}

/* ── Q&A cards ── */
.ai-qa-card {
  margin-bottom: 24px;
}
.ai-qa-card:last-child { margin-bottom: 0; }

/* ── Actions bar ── */
.ai-qa-actions {
  display: flex;
  justify-content: flex-end;
}

/* ── Head row: number + type badge ── */
.ai-qa-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.ai-qa-num {
  width: 1.375rem;
  height: 1.375rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-primary, #3b82f6);
  color: #fff;
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1;
  flex-shrink: 0;
}

/* ── Type badge ── */
.ai-qa-type-badge {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
  text-transform: capitalize;
}
.ai-qa-type--technical        { background: rgba(59, 130, 246, 0.08); color: #1d4ed8; }
.ai-qa-type--behavioral       { background: rgba(139, 92, 246, 0.08); color: #6d28d9; }
.ai-qa-type--problem_solving  { background: rgba(245, 158, 11, 0.1);  color: #b45309; }
.ai-qa-type--career           { background: rgba(22, 163, 74, 0.1);   color: #15803d; }

/* ── Question text ── */
.ai-qa-question {
  font-weight: 600;
  font-size: 0.875rem;
  line-height: 1.5;
  color: var(--color-text, #1e293b);
  margin-bottom: 0.375rem;
}

/* ── Prep tip ── */
.ai-qa-tip {
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--color-text-secondary, #64748b);
  margin: 0 0 0.5rem 0;
}

/* ── STAR ── */
.ai-qa-star {
  margin-top: 0.375rem;
  padding: 0.5rem;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 6px;
}
.ai-qa-star-row {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  margin-bottom: 0.25rem;
}
.ai-qa-star-row:last-child { margin-bottom: 0; }
.ai-qa-star-label {
  flex-shrink: 0;
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: #166534;
  color: #fff;
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1;
  margin-top: 2px;
}
.ai-qa-star-text {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: #14532d;
}
.ai-qa-star-fallback {
  font-size: 0.8125rem;
  line-height: 1.6;
  color: #14532d;
}
</style>