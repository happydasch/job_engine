<template>
  <div v-if="visible" class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal-overlay">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Configure {{ scraper?.name || scraper?.id || 'Scraper' }}</h3>
          <button class="modal-close" aria-label="Close" @click="$emit('close')">&times;</button>
        </div>
        <div v-if="loading" class="modal-loading">Loading config...</div>
        <div v-else-if="loadError" class="modal-error">{{ loadError }}</div>
        <div v-else class="modal-body">
          <div v-if="!Object.keys(fields).length" class="no-fields">
            No configuration fields available for this scraper.
          </div>
          <div v-for="(fieldDef, fieldKey) in fields" :key="fieldKey" class="config-field">
            <label class="field-label">{{ fieldDef.label || fieldKey }}</label>

            <!-- String input -->
            <input
              v-if="!fieldDef.type || fieldDef.type === 'string'"
              type="text"
              class="field-input"
              :value="formValues[fieldKey] ?? fieldDef.default ?? ''"
              @input="formValues[fieldKey] = $event.target.value"
              :placeholder="fieldDef.placeholder || ''"
            />

            <!-- Password input -->
            <input
              v-else-if="fieldDef.type === 'password'"
              type="password"
              class="field-input"
              :value="formValues[fieldKey] ?? fieldDef.default ?? ''"
              @input="formValues[fieldKey] = $event.target.value"
              :placeholder="fieldDef.placeholder || ''"
            />

            <!-- Number input -->
            <input
              v-else-if="fieldDef.type === 'number'"
              type="number"
              class="field-input"
              :value="formValues[fieldKey] ?? fieldDef.default ?? ''"
              @input="formValues[fieldKey] = Number($event.target.value)"
              :min="fieldDef.min"
              :max="fieldDef.max"
              :step="fieldDef.step || 1"
            />

            <!-- Boolean toggle -->
            <label v-else-if="fieldDef.type === 'boolean'" class="boolean-toggle">
              <input
                type="checkbox"
                :checked="!!formValues[fieldKey]"
                @change="formValues[fieldKey] = $event.target.checked"
              />
              <span class="toggle-label">{{ fieldDef.label || fieldKey }}</span>
            </label>

            <!-- Select dropdown -->
            <select
              v-else-if="fieldDef.type === 'select'"
              class="field-input"
              :value="formValues[fieldKey] ?? fieldDef.default ?? ''"
              @change="formValues[fieldKey] = $event.target.value"
            >
              <option v-if="fieldDef.placeholder" value="">{{ fieldDef.placeholder }}</option>
              <option
                v-for="opt in (fieldDef.options || [])"
                :key="opt.value ?? opt"
                :value="opt.value ?? opt"
              >{{ opt.label ?? opt }}</option>
            </select>

            <p v-if="fieldDef.description" class="field-desc">{{ fieldDef.description }}</p>
          </div>
        </div>
        <div class="modal-footer">
          <BaseButton variant="secondary" @click="$emit('close')" :disabled="saving">Cancel</BaseButton>
          <BaseButton variant="primary" @click="saveConfig" :disabled="saving || !Object.keys(fields).length">
            {{ saving ? 'Saving...' : 'Save' }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useFetch } from '../../composables/useFetch'
import { showToast } from '../../composables/useToast'
import BaseButton from '../common/BaseButton.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  scraper: { type: Object, default: null },
})
const emit = defineEmits(['close', 'saved'])

function onKeydown(e) {
  if (e.key === 'Escape' && props.visible) emit('close')
}
onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))

const fields = ref({})
const formValues = ref({})
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)

async function loadConfig() {
  if (!props.scraper?.id) return
  loading.value = true
  loadError.value = ''
  try {
    const { execute } = useFetch(`/api/scrape/scrapers/${props.scraper.id}/config`)
    const data = await execute()
    fields.value = data?.fields || {}
    const defaults = {}
    for (const [key, def] of Object.entries(fields.value)) {
      defaults[key] = data?.values?.[key] ?? def.default ?? ''
    }
    formValues.value = defaults
  } catch (e) {
    loadError.value = e.message
  }
  loading.value = false
}

async function saveConfig() {
  saving.value = true
  try {
    const res = await fetch(`/api/scrape/scrapers/${props.scraper.id}/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formValues.value),
    })
    if (res.ok) {
      showToast(`Config saved for ${props.scraper.name || props.scraper.id}`, 'success')
      emit('saved')
      emit('close')
    } else {
      const err = await res.json()
      showToast(err.detail || 'Failed to save config', 'error')
    }
  } catch (e) {
    showToast(e.message, 'error')
  }
  saving.value = false
}

watch(() => props.visible, (val) => {
  if (val) loadConfig()
})
</script>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.modal-overlay {
  position: relative; width: 100%; max-width: 520px; margin: 1rem;
}
.modal-content {
  background: var(--color-bg-card, #fff); border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden;
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border, #e2e8f0);
}
.modal-header h3 { font-size: 1rem; font-weight: 600; margin: 0; }
.modal-close {
  background: none; border: none; font-size: 1.5rem; cursor: pointer;
  color: var(--color-text-secondary, #64748b); line-height: 1;
}
.modal-close:hover { color: var(--color-text, #1e293b); }
.modal-loading, .modal-error, .no-fields {
  padding: 2rem; text-align: center; color: var(--color-text-secondary, #64748b);
  font-size: 0.875rem;
}
.modal-error { color: #991b1b; }
.modal-body { padding: 1.25rem; max-height: 50vh; overflow-y: auto; }
.config-field { margin-bottom: 1rem; }
.config-field:last-child { margin-bottom: 0; }
.field-label {
  display: block; font-size: 0.8125rem; font-weight: 500; margin-bottom: 0.375rem;
  color: var(--color-text, #1e293b);
}
.field-desc { font-size: 0.71875rem; color: var(--color-text-secondary, #64748b); margin-top: 0.25rem; }
.field-input {
  width: 100%; padding: 0.5rem 0.625rem; border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px; font-size: 0.8125rem; box-sizing: border-box;
}
.field-input:focus { outline: none; border-color: var(--color-primary, #2563eb); box-shadow: 0 0 0 2px rgba(37,99,235,0.15); }
.boolean-toggle {
  display: inline-flex; align-items: center; gap: 0.5rem;
}
.modal-footer {
  display: flex; justify-content: flex-end; gap: 0.5rem;
  padding: 0.75rem 1.25rem; border-top: 1px solid var(--color-border, #e2e8f0);
}
/* Footer buttons come from the global button system (buttons.css) via BaseButton. */
</style>