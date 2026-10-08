<template>
  <div class="settings-panel">
    <div v-if="loading" class="state-message">Loading settings...</div>
    <div v-else-if="error" class="state-message error">{{ error }}</div>
    <template v-else-if="settings">
      <div class="settings-form">

        <!-- Localization -->
        <div class="settings-group">
          <h4 class="settings-group-title">Localization</h4>
          <div class="settings-row">
            <label class="settings-label" for="settings-language">Language</label>
            <select id="settings-language" v-model="form.language" class="settings-input settings-select">
              <option value="english">English</option>
              <option value="polish">Polish</option>
              <option value="german">German</option>
              <option value="french">French</option>
              <option value="spanish">Spanish</option>
              <option value="ukrainian">Ukrainian</option>
            </select>
          </div>
          <p class="form-help">Default language for AI-generated content (cover letters, analysis).</p>

          <div class="settings-row">
            <label class="settings-label" for="settings-currency">Currency</label>
            <select id="settings-currency" v-model="form.currency" class="settings-input settings-select">
              <option value="" disabled>Select currency</option>
              <option v-for="c in availableCurrencies" :key="c.code" :value="c.code">
                {{ c.code }} &mdash; {{ c.symbol }} {{ c.name }}
              </option>
            </select>
          </div>
          <p class="form-help">Preferred currency for salary display and rate matching.</p>
        </div>

        <!-- LLM -->
        <div class="settings-group">
          <h4 class="settings-group-title">LLM Provider</h4>

          <div class="settings-row">
            <label class="settings-label" for="settings-llm-provider">Provider</label>
            <select id="settings-llm-provider" v-model="form.llm_provider" class="settings-input settings-select">
              <option value="openrouter">OpenRouter</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </div>
          <p class="form-help">Choose which LLM provider to use for AI features (analysis, cover letters, etc.).</p>

          <div class="settings-row">
            <label class="settings-label" for="settings-llm-model">Model</label>
            <input id="settings-llm-model" v-model="form.llm_model" type="text" class="settings-input" :placeholder="modelPlaceholder" />
          </div>
          <p class="form-help">{{ modelHelp }}</p>

          <div class="settings-row">
            <label class="settings-label" for="settings-llm-api-key">API Key</label>
            <input
              id="settings-llm-api-key"
              v-model="form.llm_api_key"
              type="password"
              class="settings-input"
              :placeholder="apiKeyPlaceholder"
            />
          </div>
          <p class="form-help">{{ apiKeyHelp }}</p>

        </div>

        <div v-if="editError" class="form-error">{{ editError }}</div>

        <div class="settings-actions">
          <BaseButton :loading="saving" :variant="isDirty ? 'primary' : ''" @click="save">
            {{ isDirty ? 'Save Changes' : 'Save Settings' }}
          </BaseButton>
        </div>
      </div>
    </template>
    <div v-else class="state-message">No settings data available.</div>

    <!-- Danger Zone -->
    <div class="settings-group danger-zone">
      <h4 class="settings-group-title">Danger Zone</h4>

      <div class="settings-row">
        <span class="settings-label">Database</span>
        <BaseButton variant="danger" @click="confirmResetDb = true">
          Reset Database
        </BaseButton>
      </div>
      <p class="form-help">Drop all tables and recreate them. Jobs, companies, applications, and scraper logs will be permanently deleted. Settings and profile are preserved.</p>

      <div class="settings-row">
        <span class="settings-label">Scraper</span>
        <BaseButton variant="danger" @click="confirmResetScraper = true">
          Reset Scraper
        </BaseButton>
      </div>
      <p class="form-help">Remove all scraper output JSON files, logs, and run history. The database is not affected — only the scraper-output/ directory.</p>
    </div>

    <ConfirmModal
      :visible="confirmResetDb"
      title="Reset Database"
      message="Are you sure you want to reset the database? All jobs, companies, applications, and scraper logs will be permanently deleted. This cannot be undone."
      confirm-text="Yes, Reset Database"
      :disabled="resetting"
      @confirm="handleResetDb"
      @cancel="confirmResetDb = false"
    />
    <ConfirmModal
      :visible="confirmResetScraper"
      title="Reset Scraper Data"
      message="Are you sure you want to clear all scraper output? All JSON files, logs, and run history will be permanently deleted. The database will not be affected."
      confirm-text="Yes, Reset Scraper"
      :disabled="resetting"
      @confirm="handleResetScraper"
      @cancel="confirmResetScraper = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import BaseButton from '../common/BaseButton.vue'
import ConfirmModal from '../common/ConfirmModal.vue'
import { showToast } from '../../composables/useToast'

const settings = ref(null)
const loading = ref(false)
const error = ref('')

const saving = ref(false)
const editError = ref('')

// Snapshot of form values as they were when last loaded/saved
const original = ref({})

// Form state
const form = ref({
  llm_provider: 'openrouter',
  llm_api_key: '',
  llm_model: 'openai/gpt-4o-mini',
  language: 'english',
  currency: '',
})

// Track if any setting has been changed from its original value
const isDirty = computed(() => {
  const f = form.value
  const o = original.value
  if (!o || Object.keys(o).length === 0) return false
  return (
    f.llm_provider !== (o.llm_provider || 'openrouter') ||
    f.llm_api_key !== (o.llm_api_key || '') ||
    f.llm_model !== (o.llm_model || 'openai/gpt-4o-mini') ||
    f.language !== (o.language || 'english') ||
    f.currency !== (o.currency || '')
  )
})

// Provider-dependent help text
const apiKeyPlaceholder = computed(() => {
  switch (form.value.llm_provider) {
    case 'openai': return 'sk-...'
    case 'anthropic': return 'sk-ant-...'
    default: return 'sk-or-...'
  }
})

const apiKeyHelp = computed(() => {
  switch (form.value.llm_provider) {
    case 'openai': return 'OpenAI API key for direct OpenAI access.'
    case 'anthropic': return 'Anthropic API key for Claude models.'
    default: return 'OpenRouter API key. Get one at https://openrouter.ai/keys'
  }
})

const modelPlaceholder = computed(() => {
  switch (form.value.llm_provider) {
    case 'openai': return 'gpt-4o-mini'
    case 'anthropic': return 'claude-3-haiku-20240307'
    default: return 'openai/gpt-4o-mini'
  }
})

const modelHelp = computed(() => {
  switch (form.value.llm_provider) {
    case 'openai': return 'OpenAI model name (e.g. gpt-4o-mini, gpt-4o).'
    case 'anthropic': return 'Anthropic model name (e.g. claude-3-haiku-20240307, claude-sonnet-4-20250514).'
    default: return 'OpenRouter model slug (e.g. openai/gpt-4o-mini, anthropic/claude-3.5-sonnet).'
  }
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
  } catch (e) {
    // Non-critical, fall back to empty list
    console.error('Failed to load currencies:', e)
  }
}

async function save() {
  saving.value = true
  editError.value = ''

  try {
    // Build LLM values depending on the provider
    const provider = form.value.llm_provider
    const llmValues = {
      provider,
      model: form.value.llm_model.trim(),
      api_key: form.value.llm_api_key,
      openai_api_key: form.value.llm_api_key,
      anthropic_api_key: form.value.llm_api_key,
    }

    const llmRes = await fetch('/api/app-settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section: 'llm',
        values: llmValues,
      }),
    })
    if (!llmRes.ok) {
      const body = await llmRes.text().catch(() => '')
      throw new Error(body || `HTTP ${llmRes.status}`)
    }

    // Save language + currency
    const locRes = await fetch('/api/app-settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section: 'language',
        values: form.value.language.trim().toLowerCase(),
      }),
    })
    if (!locRes.ok) {
      const body = await locRes.text().catch(() => '')
      throw new Error(body || `HTTP ${locRes.status}`)
    }

    const currRes = await fetch('/api/app-settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section: 'currency',
        values: form.value.currency.trim().toUpperCase(),
      }),
    })
    if (!currRes.ok) {
      const body = await currRes.text().catch(() => '')
      throw new Error(body || `HTTP ${currRes.status}`)
    }

    // Mirror currency to profile YAML for scorer rate matching.
    await fetch('/api/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section: 'currency',
        values: form.value.currency.trim().toUpperCase(),
      }),
    }).catch(() => {})

    showToast('Settings updated', 'success')
    // Snapshot original values so dirty flag clears
    original.value = { ...form.value }
    await loadSettings()
  } catch (e) {
    editError.value = e.message || 'Failed to save'
    showToast('Failed to save settings', 'error')
  } finally {
    saving.value = false
  }
}

async function loadSettings() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/app-settings')
    if (res.ok) {
      const data = await res.json()
      settings.value = data
      // Populate form
      form.value.llm_provider = data.llm?.provider || 'openrouter'
      form.value.llm_api_key = data.llm?.api_key || ''
      form.value.llm_model = data.llm?.model || 'openai/gpt-4o-mini'
      form.value.language = data.language || 'english'
      form.value.currency = data.currency || ''
      // Snapshot original values for dirty tracking
      original.value = { ...form.value }
    } else {
      error.value = `HTTP ${res.status}: ${res.statusText}`
    }
  } catch (e) {
    error.value = e.message || 'Failed to load settings'
  } finally {
    loading.value = false
  }
}

// ── Danger Zone ──────────────────────────────────────────────────────────────

const confirmResetDb = ref(false)
const confirmResetScraper = ref(false)
const resetting = ref(false)

async function handleResetDb() {
  resetting.value = true
  confirmResetDb.value = false
  try {
    const res = await fetch('/api/danger-zone/reset-database', { method: 'POST' })
    const data = await res.json()
    if (res.ok) {
      showToast('Database reset successfully', 'success')
      setTimeout(() => window.location.reload(), 1500)
    } else {
      showToast(data.detail || 'Reset failed', 'error')
    }
  } catch (e) {
    showToast(e.message || 'Reset failed', 'error')
  } finally {
    resetting.value = false
  }
}

async function handleResetScraper() {
  resetting.value = true
  confirmResetScraper.value = false
  try {
    const res = await fetch('/api/danger-zone/reset-scraper', { method: 'POST' })
    const data = await res.json()
    if (res.ok) {
      showToast('Scraper data reset successfully', 'success')
      setTimeout(() => window.location.reload(), 1500)
    } else {
      showToast(data.detail || 'Reset failed', 'error')
    }
  } catch (e) {
    showToast(e.message || 'Reset failed', 'error')
  } finally {
    resetting.value = false
  }
}

onMounted(() => {
  loadSettings()
  loadCurrencies()
})
</script>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.settings-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.settings-group-title {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  margin: 0 0 0.25rem 0;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--color-border, var(--border, #e2e8f0));
}

.settings-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.settings-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text, var(--text, #1e293b));
  min-width: 100px;
  flex-shrink: 0;
}

.settings-input {
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
.settings-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.settings-input::placeholder {
  color: var(--muted);
}
.settings-select {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-family: inherit;
  font-size: 13px;
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  min-height: 38px;
  box-sizing: border-box;
  appearance: auto;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.settings-select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.form-help {
  font-size: 0.6875rem;
  color: var(--color-text-secondary, var(--text-secondary, #64748b));
  margin: 0 0 12px 112px;
  line-height: 1.5;
}

.settings-actions {
  margin-top: 8px;
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

/* Danger Zone — just a red top border, everything else uses settings-group styles */
.danger-zone {
  margin-top: 1.5rem;
  padding-top: 0.5rem;
}
</style>