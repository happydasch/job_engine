<template>
  <div class="cv-uploader">
    <!-- Toolbar area -->
    <div class="toolbar-area">
      <BaseButton variant="primary" size="sm" :disabled="extracting" @click="triggerFilePicker">
        <span v-if="!extracting">Upload CV</span>
        <span v-else>Extracting...</span>
      </BaseButton>
      <span v-if="fileName" class="toolbar-area-file">{{ fileName }}</span>
      <input ref="fileInput" type="file" accept=".txt,.pdf,.md,.html,.rtf" class="cv-file-input" :disabled="extracting" @change="handleFileSelect" />
    </div>

    <!-- CV Upload inline area (shown after file is selected) -->
    <div v-if="cvText || uploadResult || errorMsg" class="cv-inline">
      <div class="cv-textarea-section">
        <textarea v-model="cvText" class="cv-textarea" rows="6" placeholder="Paste your CV text here..."></textarea>
        <div class="cv-textarea-actions">
          <BaseButton variant="primary" size="sm" :disabled="extracting || !cvText.trim()" @click="parseCvText">
            {{ extracting ? 'Analyzing...' : 'Analyze' }}
          </BaseButton>
          <BaseButton variant="soft-blue" size="sm" :disabled="improving || !cvText.trim()" @click="improveCvText">
            {{ improving ? 'Improving...' : 'Improve' }}
          </BaseButton>
          <BaseButton variant="ghost" size="sm" :disabled="extracting || improving" @click="clearCv">Clear</BaseButton>
        </div>
      </div>
      <div v-if="uploadResult" class="cv-result">
        <span class="cv-result-ok">&#10003; Profile extracted</span>
        <ul v-if="uploadResult.extracted" class="cv-extracted-fields">
          <li v-if="uploadResult.extracted.name"><strong>Name:</strong> {{ uploadResult.extracted.name }}</li>
          <li v-if="uploadResult.extracted.role"><strong>Role:</strong> {{ uploadResult.extracted.role }}</li>
          <li v-if="uploadResult.extracted.experience_years"><strong>Experience:</strong> {{ uploadResult.extracted.experience_years }} years</li>
          <li v-if="uploadResult.extracted.currency"><strong>Currency:</strong> {{ uploadResult.extracted.currency }}</li>
          <li v-if="uploadResult.extracted.skills"><strong>Skills:</strong> {{ skillCount }} categories</li>
          <li v-if="extractedExperience.length"><strong>Experience:</strong> {{ extractedExperience.length }}</li>
        </ul>
      </div>
      <div v-if="errorMsg" class="form-error">{{ errorMsg }}</div>

      <!-- CV Improvement result (shown after the user clicks Improve) -->
      <div v-if="improveResult" class="cv-improve-result">
        <div class="cv-improve-header">
          <span class="cv-improve-ok">&#10003; CV improved</span>
          <BaseButton variant="ghost" size="xs" @click="clearImproveResult" title="Dismiss">&times;</BaseButton>
        </div>
        <p v-if="improveResult.summary" class="cv-improve-summary">{{ improveResult.summary }}</p>
        <div v-if="improveResult.changes && improveResult.changes.length" class="cv-improve-changes">
          <strong class="cv-improve-changes-label">Key changes:</strong>
          <ul>
            <li v-for="(change, ci) in improveResult.changes" :key="ci">{{ change }}</li>
          </ul>
        </div>
        <div class="cv-improve-text-section">
          <strong class="cv-improve-text-label">Improved CV:</strong>
          <textarea class="cv-improve-textarea" :value="improveResult.improved_text" readonly rows="8"></textarea>
          <BaseButton size="sm" variant="soft-blue" @click="copyImprovedText">Copy to clipboard</BaseButton>
        </div>
      </div>
      <div v-if="improveError" class="form-error">{{ improveError }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { showToast } from '../../composables/useToast'
import BaseButton from '../common/BaseButton.vue'

const emit = defineEmits(['profile-updated'])

const fileInput = ref(null)
const cvText = ref('')
const extracting = ref(false)
const uploadResult = ref(null)
const errorMsg = ref('')
const fileName = ref('')

const improving = ref(false)
const improveResult = ref(null)
const improveError = ref('')

const skillCount = computed(() => {
  const s = uploadResult.value?.extracted?.skills
  return s ? Object.keys(s).length : 0
})

const extractedExperience = computed(() => {
  const e = uploadResult.value?.extracted
  return e?.experience || e?.projects || []
})

function triggerFilePicker() {
  fileInput.value?.click()
}

async function handleFileSelect(event) {
  const file = event.target.files[0]
  if (!file) return
  fileName.value = file.name
  uploadResult.value = null
  errorMsg.value = ''
  extracting.value = true

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
      errorMsg.value = 'Could not extract text from file'
    }
  } catch (e) {
    errorMsg.value = e.message || 'Failed to extract CV text'
    showToast('Failed to extract CV text', 'error')
  } finally {
    extracting.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function parseCvText() {
  if (!cvText.value || !cvText.value.trim()) return
  extracting.value = true
  errorMsg.value = ''
  uploadResult.value = null

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
    uploadResult.value = data
    showToast('Profile extracted from CV text — profile updated', 'success')
    emit('profile-updated')
  } catch (e) {
    errorMsg.value = e.message || 'Failed to parse CV text'
    showToast('Failed to parse CV', 'error')
  } finally {
    extracting.value = false
  }
}

async function improveCvText() {
  if (!cvText.value || !cvText.value.trim()) return
  improving.value = true
  improveError.value = ''
  improveResult.value = null

  try {
    const res = await fetch('/api/profile/improve-cv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: cvText.value }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(body || `HTTP ${res.status}`)
    }
    const data = await res.json()
    improveResult.value = data
    showToast('CV improved successfully', 'success')
  } catch (e) {
    improveError.value = e.message || 'Failed to improve CV'
    showToast('Failed to improve CV', 'error')
  } finally {
    improving.value = false
  }
}

function clearImproveResult() {
  improveResult.value = null
  improveError.value = ''
}

function copyImprovedText() {
  if (!improveResult.value?.improved_text) return
  navigator.clipboard.writeText(improveResult.value.improved_text)
    .then(() => showToast('Improved CV copied to clipboard', 'success'))
    .catch(() => showToast('Failed to copy', 'error'))
}

function clearCv() {
  cvText.value = ''
  uploadResult.value = null
  errorMsg.value = ''
  fileName.value = ''
  improveResult.value = null
  improveError.value = ''
}
</script>

<style scoped>
.toolbar-area {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}
.toolbar-area-file {
  font-size: 0.75rem;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}
.cv-inline {
  margin-top: 0.5rem;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--color-primary-12, rgba(37, 99, 235, 0.12));
  border-radius: 8px;
}
.cv-file-input {
  display: none;
}
.cv-inline {
  margin-top: 0.5rem;
}
.cv-textarea-section {
  margin-top: 10px;
}
.cv-textarea {
  width: 100%;
  min-height: 120px;
  padding: 8px 10px;
  border: 1px solid var(--color-border, var(--border, #e2e8f0));
  border-radius: 6px;
  font-size: 0.75rem;
  font-family: inherit;
  line-height: 1.5;
  color: var(--color-text, var(--text, #1e293b));
  background: var(--color-bg, var(--bg, #ffffff));
  resize: vertical;
  box-sizing: border-box;
}
.cv-textarea:focus {
  outline: none;
  border-color: var(--color-primary, var(--primary, #2563eb));
  box-shadow: 0 0 0 2px var(--color-primary-08, rgba(37, 99, 235, 0.12));
}
.cv-textarea-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.cv-result {
  margin-top: 10px;
  padding: 10px;
  border: 1px solid #bbf7d0;
  border-radius: 6px;
  background: #f0fdf4;
}
.cv-result-ok {
  display: block;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #166534;
  margin-bottom: 6px;
}
.cv-extracted-fields {
  margin: 0;
  padding: 0 0 0 16px;
  font-size: 0.75rem;
  color: #166534;
}
.cv-extracted-fields li {
  margin-bottom: 2px;
}
.form-error {
  font-size: 0.75rem;
  color: var(--color-danger, var(--danger, #dc2626));
  margin-top: 6px;
}

/* CV Improvement result */
.cv-improve-result {
  margin-top: 10px;
  padding: 10px;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  background: #eff6ff;
}
.cv-improve-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.cv-improve-ok {
  font-size: 0.8125rem;
  font-weight: 600;
  color: #1e40af;
}
.cv-improve-summary {
  font-size: 0.75rem;
  color: #1e3a5f;
  margin-bottom: 8px;
  line-height: 1.5;
}
.cv-improve-changes {
  margin-bottom: 8px;
}
.cv-improve-changes-label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #1e40af;
}
.cv-improve-changes ul {
  margin: 4px 0 0 0;
  padding: 0 0 0 16px;
  font-size: 0.75rem;
  color: #1e3a5f;
}
.cv-improve-changes li {
  margin-bottom: 2px;
  line-height: 1.5;
}
.cv-improve-text-section {
  margin-top: 8px;
}
.cv-improve-text-label {
  display: block;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #1e40af;
  margin-bottom: 4px;
}
.cv-improve-textarea {
  width: 100%;
  min-height: 120px;
  padding: 8px 10px;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  font-size: 0.75rem;
  font-family: inherit;
  line-height: 1.5;
  color: #1e293b;
  background: #ffffff;
  resize: vertical;
  box-sizing: border-box;
}
.cv-improve-textarea:focus {
  outline: none;
  border-color: var(--color-primary, var(--primary, #2563eb));
  box-shadow: 0 0 0 2px var(--color-primary-08, rgba(37, 99, 235, 0.12));
}
</style>