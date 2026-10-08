<template>
  <div class="catalog-sources">
    <!-- Single sources row: chips on the left, count info and button on the right -->
    <div class="sources-row">
      <div v-if="loading" class="sources-loading">Loading sources...</div>
      <EmptyState v-else-if="loadError" title="Failed to load catalog sources" :message="loadError">
        <BaseButton variant="secondary" size="sm" @click="fetchSources">Retry</BaseButton>
      </EmptyState>

      <!-- Sources list as chips — takes available space -->
      <div v-else-if="sources.length" class="sources-chips">
        <div v-for="s in sources" :key="s.id" class="source-chip">
          <button type="button" class="chip-name" @click="openEditPopup(s)" title="Edit source">{{ s.name }}</button>
          <span class="chip-type">{{ s.type }}</span>
          <button class="chip-remove" @click="confirmRemoveSource(s)" title="Remove source">&times;</button>
        </div>
      </div>
      <EmptyState v-else-if="!loading" title="No Catalog Sources Configured" message="Add a source to browse available scrapers">
        <template #icon>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5.02 8.7-5.02"/><path d="M12 22V12"/>
          </svg>
        </template>
        <div class="empty-state-actions">
          <BaseButton variant="secondary" size="sm" @click="addBundledSource">
            + Add Bundled Source
          </BaseButton>
          <BaseButton variant="primary" size="sm" @click="openAddPopup">
            + Add Custom Source
          </BaseButton>
        </div>
      </EmptyState>

      <BaseButton variant="primary" @click="openAddPopup">
        + Add Source
      </BaseButton>
    </div>

    <!-- Add/Edit Catalog Source Modal -->
    <div v-if="showModal" class="modal-backdrop" @click.self="closeModal">
      <div class="modal-overlay">
        <div class="modal-content">
          <div class="modal-header">
            <h3>{{ editingSource ? 'Edit Catalog Source' : 'Add Catalog Source' }}</h3>
            <button class="modal-close" aria-label="Close" @click="closeModal">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label class="form-label">Catalog ID</label>
              <input v-model="form.id" type="text" class="form-input" placeholder="e.g. my-registry" />
            </div>
            <div class="form-row">
              <label class="form-label">Display Name</label>
              <input v-model="form.name" type="text" class="form-input" placeholder="e.g. My Registry" />
            </div>
            <div class="form-row">
              <label class="form-label">Type</label>
              <select v-model="form.type" class="form-input" @change="onTypeChange">
                <option value="npm">npm Registry</option>
                <option value="local">Local Directory</option>
                <option value="git">Git Repository</option>
              </select>
            </div>
            <div v-if="form.type === 'npm'" class="form-row">
              <label class="form-label">npm Scope</label>
              <input v-model="form.scope" type="text" class="form-input" placeholder="@job-engine-scrapers" />
            </div>
            <div v-if="form.type === 'npm'" class="form-row">
              <label class="form-label">Registry URL</label>
              <input v-model="form.registry" type="text" class="form-input" placeholder="https://registry.npmjs.org" />
            </div>
            <div v-if="form.type === 'local'" class="form-row">
              <label class="form-label">Local Path</label>
              <input v-model="form.path" type="text" class="form-input" placeholder="./packages/job-engine-scrapers/scrapers" />
            </div>
            <div v-if="form.type === 'git'" class="form-row">
              <label class="form-label">Git URL</label>
              <input v-model="form.repoUrl" type="text" class="form-input" placeholder="https://github.com/user/repo.git" />
            </div>
            <div v-if="form.type === 'git'" class="form-row">
              <label class="form-label">Branch/Ref</label>
              <input v-model="form.branch" type="text" class="form-input" placeholder="main" />
            </div>
          </div>
          <div class="modal-footer">
            <span v-if="formError" class="form-error">{{ formError }}</span>
            <BaseButton variant="secondary" @click="closeModal">Cancel</BaseButton>
            <BaseButton variant="primary" @click="submitForm" :disabled="submitting">
              {{ submitting ? 'Saving...' : (editingSource ? 'Update' : 'Add') }}
            </BaseButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Confirm Delete Modal -->
    <ConfirmModal
      :visible="showDeleteConfirm"
      title="Remove Catalog Source"
      :message="`Delete catalog source &quot;${deletingSource?.name || deletingSource?.id}&quot;? This cannot be undone.`"
      confirm-text="Delete"
      confirm-variant="danger"
      :disabled="deleting"
      @confirm="doRemoveSource"
      @cancel="showDeleteConfirm = false; deletingSource = null"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, reactive } from 'vue'
import { useFetch } from '../../composables/useFetch.js'
import { showToast } from '../../composables/useToast.js'
import BaseButton from '../common/BaseButton.vue'
import ConfirmModal from '../common/ConfirmModal.vue'

const emit = defineEmits(['sources-changed'])

function onKeydown(e) {
  if (e.key === 'Escape' && showModal.value) closeModal()
}
onUnmounted(() => document.removeEventListener('keydown', onKeydown))

const sources = ref([])
const loading = ref(false)
const loadError = ref(null)

// Modal state
const showModal = ref(false)
const editingSource = ref(null)
const submitting = ref(false)
const formError = ref('')
const form = reactive({
  id: '',
  name: '',
  type: 'npm',
  scope: '',
  registry: '',
  path: '',
  repoUrl: '',
  branch: 'main',
})

// Delete confirm state
const showDeleteConfirm = ref(false)
const deletingSource = ref(null)
const deleting = ref(false)

function resetForm() {
  form.id = ''
  form.name = ''
  form.type = 'npm'
  form.scope = ''
  form.registry = ''
  form.path = ''
  form.repoUrl = ''
  form.branch = 'main'
  formError.value = ''
}

function openAddPopup() {
  editingSource.value = null
  resetForm()
  showModal.value = true
}

function openEditPopup(s) {
  editingSource.value = s
  form.id = s.id || ''
  form.name = s.name || ''
  form.type = s.type || 'npm'
  form.scope = s.scope || ''
  form.registry = s.registry || ''
  form.path = s.path || ''
  form.repoUrl = s.repository_url || ''
  form.branch = s.branch || 'main'
  formError.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingSource.value = null
}

function onTypeChange() {
  // Clear fields that are irrelevant for the selected type
}

async function submitForm() {
  if (!form.name.trim()) {
    formError.value = 'Name is required'
    return
  }
  submitting.value = true
  formError.value = ''
  try {
    const body = { name: form.name.trim(), type: form.type }
    if (form.id) body.id = form.id
    if (form.type === 'npm') {
      body.scope = form.scope
      body.registry = form.registry
    } else if (form.type === 'local') {
      body.path = form.path
    } else if (form.type === 'git') {
      body.repository_url = form.repoUrl
      body.branch = form.branch
    }

    let res
    if (editingSource.value) {
      res = await fetch(`/api/scrapers/catalog/catalogs/${editingSource.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } else {
      res = await fetch('/api/scrapers/catalog/catalogs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    }

    if (res.ok) {
      showToast(`Catalog source ${editingSource.value ? 'updated' : 'added'}`, 'success')
      closeModal()
      await fetchSources()
      emit('sources-changed')
    } else {
      const err = await res.json()
      formError.value = err.detail || (editingSource.value ? 'Failed to update source' : 'Failed to add source')
    }
  } catch (e) {
    formError.value = e.message
  }
  submitting.value = false
}

function confirmRemoveSource(s) {
  deletingSource.value = s
  showDeleteConfirm.value = true
}

async function doRemoveSource() {
  if (!deletingSource.value) return
  deleting.value = true
  try {
    const res = await fetch(`/api/scrapers/catalog/catalogs/${deletingSource.value.id}`, { method: 'DELETE' })
    if (res.ok) {
      showToast('Catalog source removed', 'success')
      showDeleteConfirm.value = false
      deletingSource.value = null
      await fetchSources()
      emit('sources-changed')
    } else {
      const err = await res.json()
      showToast(err.detail || 'Failed to remove source', 'error')
    }
  } catch (e) {
    showToast(e.message, 'error')
  }
  deleting.value = false
}

async function fetchSources() {
  loading.value = true
  loadError.value = null
  try {
    const { execute } = useFetch('/api/scrapers/catalog/catalogs')
    const data = await execute()
    sources.value = data?.catalogs || []
  } catch (e) {
    loadError.value = e.message || 'Unknown error'
  }
  loading.value = false
}

onMounted(() => {
  fetchSources()
  document.addEventListener('keydown', onKeydown)
})

const addingBundled = ref(false)

async function addBundledSource() {
  if (addingBundled.value) return
  addingBundled.value = true
  try {
    const res = await fetch('/api/scrapers/catalog/catalogs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: 'bundled',
        name: 'Bundled job-engine-scrapers',
        type: 'local',
        path: 'packages/job-engine-scrapers/scrapers',
      }),
    })
    if (res.ok) {
      showToast('Bundled catalog source added', 'success')
      await fetchSources()
      emit('sources-changed')
    } else {
      const err = await res.json()
      showToast(err.detail || 'Failed to add bundled source', 'error')
    }
  } catch (e) {
    showToast(e.message, 'error')
  }
  addingBundled.value = false
}
</script>

<style scoped>
.catalog-sources { }
.sources-row {
  display: flex; align-items: center; gap: 0.5rem; flex-wrap: nowrap;
}
/* Chips take available space on the left */
.sources-chips {
  flex: 1; min-width: 0;
  display: flex; flex-wrap: wrap; gap: 0.375rem;
}
.sources-loading, .sources-empty {
  flex: 1; min-width: 0;
  font-size: 0.75rem; color: var(--color-text-secondary, #64748b);
  padding: 0.25rem 0; text-align: left;
}
.count-total { font-size: 0.75rem; color: var(--color-text-secondary, #64748b); }
.source-chip {
  display: inline-flex; align-items: center; gap: 0.375rem;
  background: var(--color-bg-secondary, #f8fafc); border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 999px; padding: 0.25rem 0.6rem 0.25rem 0.5rem; font-size: 0.71875rem;
}
.chip-name { font-weight: 500; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; font-size: 0.75rem; color: var(--color-text, #1e293b); background: none; border: none; padding: 0; font-family: inherit; }
.chip-name:hover { color: var(--color-primary, #2563eb); text-decoration: underline; }
.chip-type { font-size: 0.6rem; color: var(--color-text-secondary, #64748b); text-transform: uppercase; font-weight: 500; }
.chip-remove {
  background: none; border: none; cursor: pointer; font-size: 0.9rem; line-height: 1;
  color: var(--color-text-secondary, #64748b); padding: 0; margin-left: 0.125rem;
  transition: color 0.15s;
}
.chip-remove:hover { color: #991b1b; }
/* Buttons come from the global button system (buttons.css) via BaseButton. */

/* Modal styles */
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.modal-overlay {
  position: relative; width: 100%; max-width: 480px; margin: 1rem;
}
.modal-content {
  background: var(--color-bg-card, #fff); border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden;
}
.modal-sm .modal-content { max-width: 400px; }
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
.modal-body { padding: 1.25rem; max-height: 60vh; overflow-y: auto; }
.modal-body p { font-size: 0.875rem; color: var(--color-text, #1e293b); margin: 0; }
.modal-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 0.5rem;
  padding: 0.75rem 1.25rem; border-top: 1px solid var(--color-border, #e2e8f0);
}
.form-error {
  font-size: 0.75rem; color: #991b1b; margin-right: auto;
}
.form-row { margin-bottom: 0.75rem; }
.form-row:last-child { margin-bottom: 0; }
.form-label { display: block; font-size: 0.78125rem; font-weight: 500; margin-bottom: 0.25rem; color: var(--color-text, #1e293b); }
.form-input {
  width: 100%; padding: 0.5rem 0.625rem; border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px; font-size: 0.8125rem; box-sizing: border-box;
}
.form-input:focus { outline: none; border-color: var(--color-primary, #2563eb); box-shadow: 0 0 0 2px rgba(37,99,235,0.15); }
.empty-state-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
  justify-content: center;
}
</style>