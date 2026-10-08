<template>
  <div class="profile-panel">
    <div v-if="loading" class="state-message">Loading profile...</div>
    <div v-else-if="error" class="state-message error">{{ error }}</div>
    <template v-else-if="profile">
      <!-- CV Upload area -->
      <CvUploader @profile-updated="loadProfile" />

      <!-- Basic Info (Name, Role, Rate, Preferences) -->
      <ProfileSection title="Basic Info" description="Your name, role, salary range, location, and remote/work preferences. Used for experience_fit (4%), rate_fit (12%), and location_fit (8%) scoring." weight="24%">
        <template #header-extra>
          <BaseButton v-if="editingSection !== 'basic'" variant="link" size="sm" @click.stop="startEdit('basic')">Edit</BaseButton>
        </template>
        <div v-if="editingSection === 'basic'" class="edit-body">
          <div class="profile-edit-row">
            <span class="profile-label">Name</span>
            <input v-model="form.name" class="profile-input" type="text" placeholder="Your name" aria-label="Name" />
          </div>
          <div class="profile-edit-row">
            <span class="profile-label">Role</span>
            <input v-model="form.role" class="profile-input" type="text" placeholder="e.g. Senior Software Engineer" aria-label="Role" />
          </div>
          <div class="profile-edit-row">
            <span class="profile-label">Experience</span>
            <input v-model="form.experience_years" class="profile-input" type="number" min="0" max="50" placeholder="Years" aria-label="Years of experience" />
          </div>
          <div class="profile-section-divider"></div>
          <div class="profile-edit-row">
            <span class="profile-label">Min Monthly</span>
            <input v-model="form.rate_min" class="profile-input" type="number" min="0" placeholder="e.g. 5000" aria-label="Minimum rate" />
          </div>
          <div class="profile-edit-row">
            <span class="profile-label">Max Monthly</span>
            <input v-model="form.rate_max" class="profile-input" type="number" min="0" placeholder="e.g. 12000" aria-label="Maximum rate" />
          </div>
          <div class="profile-edit-row">
            <span class="profile-label">Currency</span>
            <select v-model="form.currency" class="profile-input profile-select" aria-label="Currency">
              <option value="" disabled>Select currency</option>
              <option v-for="c in availableCurrencies" :key="c.code" :value="c.code">
                {{ c.code }} &mdash; {{ c.symbol }} {{ c.name }}
              </option>
            </select>
          </div>
          <div class="profile-section-divider"></div>
          <div class="profile-edit-row">
            <span class="profile-label">Locations</span>
            <input v-model="form.preferred_locations" class="profile-input" type="text" placeholder="e.g. Warsaw, Krakow, Remote" aria-label="Preferred locations" />
          </div>
          <div class="profile-edit-row">
            <span class="profile-label">Excluded Cos</span>
            <input v-model="form.excluded_companies" class="profile-input" type="text" placeholder="e.g. CompanyA, CompanyB" aria-label="Excluded companies" />
          </div>
          <div class="profile-edit-row">
            <label class="profile-check-label">
              <input v-model="form.remote_only" type="checkbox" />
              Remote Only
            </label>
          </div>
          <div v-if="editError" class="form-error">{{ editError }}</div>
          <ProfileEditActions :saving="saving" @save="save('basic')" @cancel="cancelEdit" />
        </div>
        <div v-else>
          <div class="field-row"><span class="field-label">Name</span><span class="field-value">{{ profile.name || '&mdash;' }}</span></div>
          <div class="field-row"><span class="field-label">Role</span><span class="field-value">{{ profile.role || '&mdash;' }}</span></div>
          <div class="field-row"><span class="field-label">Experience</span><span class="field-value">{{ profile.experience_years != null ? profile.experience_years + ' years' : '&mdash;' }}</span></div>
          <div class="field-row"><span class="field-label">Monthly</span><span class="field-value">{{ profile.rate ? formatCurrency(profile.rate.min_monthly) + ' - ' + formatCurrency(profile.rate.max_monthly) + ' ' + (profile.rate?.currency || '') : 'Not set' }}</span></div>
          <div class="field-row"><span class="field-label">Remote Only</span><span class="field-value">{{ profile.remote_only ? 'Yes' : 'No' }}</span></div>
          <div class="field-row"><span class="field-label">Location</span><span class="field-value">{{ formatLocations(profile.preferred_locations) }}</span></div>
          <div class="field-row"><span class="field-label">Excluded</span><span class="field-value">{{ formatList(profile.excluded_companies) }}</span></div>
        </div>
      </ProfileSection>

      <!-- Experience -->
      <ProfileSection title="Experience" description="Your notable projects and professional experience. Not directly scored, but used for cover letter generation and job application context." weight="">
        <template #header-extra>
          <BaseButton v-if="editingSection !== 'experience'" variant="link" size="sm" @click.stop="startEdit('experience')">Edit</BaseButton>
        </template>
        <div v-if="editingSection === 'experience'" class="edit-body">
          <div v-for="(exp, ei) in form.experience_list" :key="ei" class="exp-card">
            <div class="exp-card-header">
              <span class="exp-card-label">Experience {{ ei + 1 }}</span>
              <BaseButton variant="ghost" size="xs" @click="removeExperience(ei)" title="Remove experience">&times;</BaseButton>
            </div>
            <input v-model="exp.name" class="profile-input exp-name-input" type="text" placeholder="Project / role name" aria-label="Project or role name" />
            <textarea v-model="exp.description" class="profile-textarea exp-desc-input" rows="2" placeholder="Description (optional)" aria-label="Experience description"></textarea>
          </div>
          <BaseButton variant="soft-blue" size="sm" @click="addExperience">+ Add Experience</BaseButton>
          <div v-if="editError" class="form-error">{{ editError }}</div>
          <ProfileEditActions :saving="saving" @save="save('experience')" @cancel="cancelEdit" />
        </div>
        <div v-else>
          <div v-if="profile.experience && profile.experience.length">
            <div v-for="(exp, i) in profile.experience" :key="i" class="experience-item">
              <div class="experience-name">{{ exp.name }}</div>
              <div v-if="exp.description" class="experience-desc">{{ exp.description }}</div>
            </div>
          </div>
          <div v-else class="field-row"><span class="field-value text-muted">No experience listed</span></div>
        </div>
      </ProfileSection>

      <!-- Skills + Critical Categories + Boosted Keywords -->
      <ProfileSection title="Skills" description="Your skills grouped by category. Mark categories with the star to make them critical (bonus), and star individual skills to boost them (15% weight). Used for skill_overlap (25%), critical bonus, and keyword_boost scoring." weight="40%">
        <template #header-extra>
          <BaseButton v-if="editingSection !== 'skills'" variant="link" size="sm" @click.stop="startEdit('skills')">Edit</BaseButton>
        </template>
        <div v-if="editingSection === 'skills'" class="edit-body">
          <CategoryEditor v-model="form.skills_categories" cat-placeholder="Category name" item-placeholder="Add skill + Enter" add-label="Add Category" />
          <div v-if="editError" class="form-error">{{ editError }}</div>
          <ProfileEditActions :saving="saving" @save="save('skills')" @cancel="cancelEdit" />
        </div>
        <div v-else>
          <div v-if="hasSkills">
            <div v-for="(skills, category) in profile.skills" :key="category" class="skill-group">
              <span class="skill-category-label" :class="{ 'label-critical': isCriticalCategory(category) }">
                {{ category }}
                <span v-if="isCriticalCategory(category)" class="crit-badge" title="Critical category">&#9733;</span>
              </span>
              <div class="tag-list">
                <span v-for="s in skills" :key="s" class="tag" :class="{ 'tag-boosted': isBoostedKeyword(s) }">
                  {{ s }}
                  <span v-if="isBoostedKeyword(s)" class="boost-indicator" title="Boosted keyword">&#9733;</span>
                </span>
              </div>
            </div>
          </div>
          <div v-else class="field-row"><span class="field-value text-muted">No skills configured</span></div>
        </div>
      </ProfileSection>

      <!-- Career Goals -->
      <ProfileSection title="Career Goals" description="Your long-term career trajectory used for career_alignment scoring (15% weight). Add industries, roles, and domains you want to grow into." weight="15%">
        <template #header-extra>
          <BaseButton v-if="editingSection !== 'career_goals'" variant="link" size="sm" @click.stop="startEdit('career_goals')">Edit</BaseButton>
        </template>
        <div v-if="editingSection === 'career_goals'" class="edit-body">
          <div class="tag-input-area">
            <span v-for="(item, i) in form.career_goals_list" :key="i" class="tag tag-goal">
              {{ item }}
              <button class="tag-remove" @click="removeCareerGoal(i)">&times;</button>
            </span>
            <input class="tag-text-input" type="text" placeholder="Add goal + Enter" aria-label="Add career goal" @keydown.enter.prevent="addCareerGoal" />
          </div>
          <div v-if="editError" class="form-error">{{ editError }}</div>
          <ProfileEditActions :saving="saving" @save="save('career_goals')" @cancel="cancelEdit" />
        </div>
        <div v-else>
          <div v-if="hasCareerGoals" class="tag-list">
            <span v-for="item in profile.career_goals" :key="item" class="tag tag-goal">{{ item }}</span>
          </div>
          <div v-else class="field-row"><span class="field-value text-muted">None</span></div>
        </div>
      </ProfileSection>

      <!-- Behavioral Keywords -->
      <ProfileSection title="Behavioral Keywords" description="Culture-fit keywords used for behavioral_fit scoring (13% weight). Matched against job descriptions to find companies aligned with your work style." weight="13%">
        <template #header-extra>
          <BaseButton v-if="editingSection !== 'behavioral_keywords'" variant="link" size="sm" @click.stop="startEdit('behavioral_keywords')">Edit</BaseButton>
        </template>
        <div v-if="editingSection === 'behavioral_keywords'" class="edit-body">
          <div class="tag-input-area">
            <span v-for="(item, i) in form.behavioral_keywords_list" :key="i" class="tag tag-behavioral">
              {{ item }}
              <button class="tag-remove" @click="removeBehavioral(i)">&times;</button>
            </span>
            <input class="tag-text-input" type="text" placeholder="Add keyword + Enter" aria-label="Add behavioral keyword" @keydown.enter.prevent="addBehavioral" />
          </div>
          <div v-if="editError" class="form-error">{{ editError }}</div>
          <ProfileEditActions :saving="saving" @save="save('behavioral_keywords')" @cancel="cancelEdit" />
        </div>
        <div v-else>
          <div v-if="hasBehavioral" class="tag-list">
            <span v-for="item in profile.behavioral_keywords" :key="item" class="tag tag-behavioral">{{ item }}</span>
          </div>
          <div v-else class="field-row"><span class="field-value text-muted">None</span></div>
        </div>
      </ProfileSection>

    </template>
    <div v-else class="state-message">No profile data available.</div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import BaseButton from '../common/BaseButton.vue'
import ProfileSection from '../profile/ProfileSection.vue'
import ProfileEditActions from '../profile/ProfileEditActions.vue'
import CategoryEditor from '../profile/CategoryEditor.vue'
import CvUploader from './CvUploader.vue'
import { showToast } from '../../composables/useToast'

const profile = ref(null)
const loading = ref(false)
const error = ref('')

const editingSection = ref(null)
const saving = ref(false)
const editError = ref('')

// Form state for inline editing
const form = ref({
  name: '',
  role: '',
  experience_years: null,
  rate_min: null,
  rate_max: null,
  currency: '',
  skills_categories: [],
  behavioral_keywords_list: [],
  experience_list: [],
  career_goals_list: [],
  remote_only: false,
  preferred_locations: '',
  excluded_companies: '',
})


// CV upload state
const fileInput = ref(null)
const cvText = ref('')
const cvExtracting = ref(false)
const cvUploadResult = ref(null)
const cvError = ref('')
const cvFileName = ref('')



const skillCount = computed(() => {
  const s = cvUploadResult.value?.extracted?.skills
  return s ? Object.keys(s).length : 0
})

const hasSkills = computed(() => {
  const s = profile.value?.skills
  return s && typeof s === 'object' && Object.keys(s).length > 0
})

const hasBehavioral = computed(() => {
  const b = profile.value?.behavioral_keywords
  return Array.isArray(b) && b.length > 0
})

const hasCareerGoals = computed(() => {
  const c = profile.value?.career_goals
  return Array.isArray(c) && c.length > 0
})

// Available currencies from API
const availableCurrencies = ref([])
async function loadCurrencies() {
  try {
    const res = await fetch('/api/currencies')
    if (res.ok) {
      const data = await res.json()
      availableCurrencies.value = data.currencies || []
    }
  } catch {
    // Non-critical, fall back to empty list
  }
}

function formatCurrency(val) {
  if (val == null) return '\u2014'
  return new Intl.NumberFormat('en-US').format(val)
}

function formatLocations(locs) {
  if (!locs || !locs.length) return '\u2014'
  return locs.join(', ')
}

function formatList(items) {
  if (!items || !items.length) return 'None'
  return items.join(', ')
}

function startEdit(section) {
  const p = profile.value
  editError.value = ''

  switch (section) {
    case 'basic':
      form.value.name = p.name || ''
      form.value.role = p.role || ''
      form.value.experience_years = p.experience_years ?? null
      form.value.rate_min = p.rate?.min_monthly ?? null
      form.value.rate_max = p.rate?.max_monthly ?? null
      form.value.currency = p.rate?.currency || p.currency || ''
      form.value.remote_only = p.remote_only || false
      form.value.preferred_locations = Array.isArray(p.preferred_locations) ? p.preferred_locations.join(', ') : ''
      form.value.excluded_companies = Array.isArray(p.excluded_companies) ? p.excluded_companies.join(', ') : ''
      break
    case 'skills':
      form.value.skills_categories = p.skills && typeof p.skills === 'object'
        ? Object.entries(p.skills).map(([category, items]) => ({
            category,
            critical: Array.isArray(p.critical_categories) && p.critical_categories.includes(category),
            items: items.map(name => ({
              name,
              boosted: Array.isArray(p.boosted_keywords) && p.boosted_keywords.includes(name),
            })),
          }))
        : []
      break
    case 'experience':
      form.value.experience_list = Array.isArray(p.experience)
        ? p.experience.map(exp => ({ name: exp.name || '', description: exp.description || '' }))
        : Array.isArray(p.projects)
          ? p.projects.map(proj => ({ name: proj.name || '', description: proj.description || '' }))
          : []
      break
    case 'behavioral_keywords':
      {
        form.value.behavioral_keywords_list = Array.isArray(p.behavioral_keywords) ? [...p.behavioral_keywords] : []
      }
      break
    case 'career_goals':
      {
        form.value.career_goals_list = Array.isArray(p.career_goals) ? [...p.career_goals] : []
      }
      break
  }

  editingSection.value = section
}

function cancelEdit() {
  editError.value = ''
  editingSection.value = null
}

async function save(section) {
  saving.value = true
  editError.value = ''

  try {
    const values = buildValues(section)

    if (section === 'skills') {
      // Skills section returns 3 separate values that need individual PATCH calls
      const patches = [
        fetch('/api/profile', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ section: 'skills', values: values.skills }),
        }),
        fetch('/api/profile', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ section: 'critical_categories', values: values.critical_categories }),
        }),
        fetch('/api/profile', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ section: 'boosted_keywords', values: values.boosted_keywords }),
        }),
      ]
      const results = await Promise.all(patches)
      for (const res of results) {
        if (!res.ok) {
          const body = await res.text().catch(() => '')
          throw new Error(body || `HTTP ${res.status}`)
        }
      }
    } else {
      const res = await fetch('/api/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section, values }),
      })
      if (!res.ok) {
        const body = await res.text().catch(() => '')
        throw new Error(body || `HTTP ${res.status}`)
      }
    }

    showToast('Profile updated', 'success')
    editingSection.value = null
    await loadProfile()
  } catch (e) {
    editError.value = e.message || 'Failed to save'
    showToast('Failed to save profile', 'error')
  } finally {
    saving.value = false
  }
}

// Helper: check if a category name is in the critical_categories list
function isCriticalCategory(category) {
  return profile.value && Array.isArray(profile.value.critical_categories) && profile.value.critical_categories.includes(category)
}

// Helper: check if a skill name is in the boosted_keywords list
function isBoostedKeyword(skill) {
  return profile.value && Array.isArray(profile.value.boosted_keywords) && profile.value.boosted_keywords.includes(skill)
}

function buildValues(section) {
  switch (section) {
    case 'basic':
      return {
        name: form.value.name.trim(),
        role: form.value.role.trim(),
        experience_years: form.value.experience_years != null ? Number(form.value.experience_years) : null,
        min_monthly: form.value.rate_min != null ? Number(form.value.rate_min) : null,
        max_monthly: form.value.rate_max != null ? Number(form.value.rate_max) : null,
        currency: form.value.currency.trim().toUpperCase(),
        remote_only: form.value.remote_only,
        preferred_locations: parseCommaList(form.value.preferred_locations),
        excluded_companies: parseCommaList(form.value.excluded_companies),
      }
    case 'skills':
      return {
        skills: categoriesToObject(form.value.skills_categories),
        critical_categories: form.value.skills_categories
          .filter(cat => cat.critical)
          .map(cat => cat.category.trim())
          .filter(Boolean),
        boosted_keywords: form.value.skills_categories
          .flatMap(cat => cat.items)
          .filter(item => item.boosted)
          .map(item => item.name.trim())
          .filter(Boolean),
      }
    case 'critical_categories':
      return parseCommaList(form.value.critical_categories)
    case 'boosted_keywords':
      return parseCommaList(form.value.boosted_keywords)
    case 'experience':
      return form.value.experience_list.map(exp => ({ name: exp.name.trim(), description: exp.description.trim() })).filter(exp => exp.name)
    case 'behavioral_keywords':
      return [...form.value.behavioral_keywords_list]
    case 'career_goals':
      return [...form.value.career_goals_list]
    default:
      return {}
  }
}

function parseCommaList(str) {
  if (!str || !str.trim()) return []
  return str.split(',').map(s => s.trim()).filter(Boolean)
}

function categoriesToObject(categories) {
  const obj = {}
  for (const cat of categories) {
    const key = (cat.key || cat.category).trim()
    if (!key) continue
    // Support both old format (plain strings) and new format ({ name, boosted })
    const items = cat.items
      .map(i => (typeof i === 'string' ? i : i.name))
      .filter(i => i.trim())
    if (items.length) obj[key] = items
  }
  return obj
}

// Experience helpers
function addExperience() {
  form.value.experience_list.push({ name: '', description: '' })
}
function removeExperience(index) {
  form.value.experience_list.splice(index, 1)
}
// Career goal tag helpers
function addCareerGoal(event) {
  const val = event.target.value.trim()
  if (!val) return
  form.value.career_goals_list.push(val)
  event.target.value = ''
}
function removeCareerGoal(index) {
  form.value.career_goals_list.splice(index, 1)
}

// Behavioral keyword tag helpers
function addBehavioral(event) {
  const val = event.target.value.trim()
  if (!val) return
  form.value.behavioral_keywords_list.push(val)
  event.target.value = ''
}
function removeBehavioral(index) {
  form.value.behavioral_keywords_list.splice(index, 1)
}

// CV upload handlers
function triggerFilePicker() {
  fileInput.value?.click()
}
async function handleFileSelect(event) {
  const file = event.target.files[0]
  if (!file) return
  cvFileName.value = file.name
  cvUploadResult.value = null
  cvError.value = ''
  cvExtracting.value = true

  // Upload file to extract text, show it in textarea for editing
  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await fetch('/api/profile/upload-cv', {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(body || `HTTP ${res.status}`)
    }
    const data = await res.json()
    if (data.text) {
      cvText.value = data.text
    } else {
      cvError.value = 'Could not extract text from file'
    }
  } catch (e) {
    cvError.value = e.message || 'Failed to extract CV text'
    showToast('Failed to extract CV text', 'error')
  } finally {
    cvExtracting.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function parseCvText() {
  if (!cvText.value || !cvText.value.trim()) return
  cvExtracting.value = true
  cvError.value = ''
  cvUploadResult.value = null

  try {
    const res = await fetch('/api/profile/parse-cv-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: cvText.value }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(body || `HTTP ${res.status}`)
    }
    const data = await res.json()
    cvUploadResult.value = data
    showToast('Profile extracted from CV text — profile updated', 'success')
    await loadProfile()
  } catch (e) {
    cvError.value = e.message || 'Failed to parse CV text'
    showToast('Failed to parse CV', 'error')
  } finally {
    cvExtracting.value = false
  }
}

function clearCvText() {
  cvText.value = ''
  cvUploadResult.value = null
  cvError.value = ''
  cvFileName.value = ''
}

async function loadProfile() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/profile/data')
    if (res.ok) {
      profile.value = await res.json()
    } else {
      error.value = `HTTP ${res.status}: ${res.statusText}`
    }
  } catch (e) {
    error.value = e.message || 'Failed to load profile'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadProfile()
  loadCurrencies()
})
</script>

<style scoped>
.profile-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

/* Fields */
.field-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 0.25rem 0;
  font-size: 0.8125rem;
  gap: 0.5rem;
}
.field-label {
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  white-space: nowrap;
  flex-shrink: 0;
}
.field-value {
  color: var(--color-text, var(--text, #1e293b));
  text-align: right;
  word-break: break-word;
}
.text-muted {
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
}

/* Tags */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.25rem;
}
.tag {
  display: inline-block;
  padding: 0.1875rem 0.5rem;
  font-size: 0.71875rem;
  border-radius: 4px;
  background: var(--color-primary-08, rgba(37, 99, 235, 0.08));
  color: var(--color-primary, var(--primary, #2563eb));
}
.tag-boosted {
  background: var(--color-profile-boosted-bg, rgba(245, 158, 11, 0.12));
  color: var(--color-profile-boosted, #b45309);
}
.boost-indicator {
  margin-left: 2px;
  font-size: 0.625rem;
}
.tag-behavioral {
  background: var(--color-profile-behavioral-bg, rgba(22, 163, 74, 0.08));
  color: var(--color-profile-behavioral, #16a34a);
}
.tag-goal {
  background: var(--color-profile-goal-bg, rgba(139, 92, 246, 0.08));
  color: var(--color-profile-goal, #7c3aed);
}
/* Tag input area (pills with inline text input) */
.tag-input-area {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  align-items: center;
  padding: 0.5rem;
  background: var(--surface, #ffffff);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 6px;
  min-height: 2.25rem;
}
.tag-input-area:focus-within {
  border-color: var(--color-primary, var(--primary, #2563eb));
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.tag-text-input {
  flex: 1;
  min-width: 100px;
  border: none !important;
  outline: none !important;
  padding: 0.25rem 0.125rem;
  font-size: 0.71875rem;
  background: transparent;
  color: var(--text, #1e293b);
  box-shadow: none !important;
}
.tag-text-input::placeholder {
  color: #94a3b8;
}
.tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
  margin-left: 2px;
  color: inherit;
  opacity: 0.5;
  display: inline-flex;
  align-items: center;
  border-radius: 3px;
  transition: opacity 0.1s, background 0.1s;
}
.tag-remove:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.06);
}


/* Skill groups */
.skill-group {
  margin-bottom: 0.5rem;
}
.skill-group:last-child {
  margin-bottom: 0;
}
.skill-category-label {
  display: inline-block;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.025em;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  margin-bottom: 0.25rem;
}
.label-critical {
  color: #b45309;
}
.crit-badge {
  margin-left: 3px;
  font-size: 0.625rem;
  color: #d97706;
}

/* Experience */
.experience-item {
  margin-bottom: 0.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-border, var(--border, #e2e8f0));
}
.experience-item:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}
.experience-name {
  font-weight: 600;
  font-size: 0.8125rem;
  color: var(--color-text, var(--text, #1e293b));
}
.experience-desc {
  font-size: 0.75rem;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  margin-top: 0.125rem;
}


/* States */
.state-message {
  text-align: center;
  padding: 2rem;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  font-size: 0.875rem;
}
.state-message.error {
  color: #dc2626;
}

/* ===== Inline editing styles ===== */
.edit-body {
  background: var(--color-bg, var(--bg, #f8f9fa));
  border: 1px solid var(--color-border, var(--border, #e2e8f0));
  border-radius: 6px;
  margin: -0.625rem -0.75rem;
  padding: 0.75rem;
}

.profile-edit-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
}
.profile-edit-row:last-of-type {
  margin-bottom: 0;
}
.profile-section-divider {
  height: 1px;
  background: var(--color-border, var(--border, #e2e8f0));
  margin: 4px 0 10px;
}
.profile-label {
  font-size: 0.6875rem;
  font-weight: 600;
  min-width: 100px;
  flex-shrink: 0;
  padding-top: 8px;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  letter-spacing: 0.3px;
}
.profile-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border, var(--border, #e2e8f0));
  border-radius: 6px;
  font-size: 0.8125rem;
  font-family: inherit;
  color: var(--color-text, var(--text, #1e293b));
  background: var(--surface, #ffffff);
  resize: vertical;
  box-sizing: border-box;
  line-height: 1.6;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.profile-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-family: inherit;
  font-size: 13px;
  background: var(--surface);
  color: var(--text);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.profile-input:focus,
.profile-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--focus-ring);
}
.profile-textarea:focus {
  outline: none;
  border-color: var(--color-primary, var(--primary, #2563eb));
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.profile-textarea::placeholder {
  color: #94a3b8;
}
.profile-check-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8125rem;
  cursor: pointer;
  color: var(--color-text, var(--text, #1e293b));
}
.profile-check-label input {
  accent-color: var(--color-primary, var(--primary, #2563eb));
  width: 14px;
  height: 14px;
}
.form-help {
  font-size: 0.6875rem;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  margin-bottom: 8px;
  line-height: 1.5;
}
.form-help code {
  background: var(--gray-100, #f1f5f9);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.625rem;
}
/* ===== Visual form styles for experience ===== */
.exp-card {
  margin-bottom: 10px;
  padding: 10px;
  background: var(--surface, #ffffff);
  border: 1px solid var(--color-border, var(--border, #e2e8f0));
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.exp-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.exp-card-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  letter-spacing: 0.3px;
}
.exp-name-input {
  width: 100%;
}
.exp-desc-input {
  width: 100%;
}

.form-error {
  margin-top: 8px;
  padding: 6px 10px;
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
  border-radius: 6px;
  font-size: 0.75rem;
}

/* Select dropdown for currency */
.profile-select {
  appearance: auto;
  cursor: pointer;
  min-height: 34px;
}</style>