<template>
  <div class="catalog-view">

    <!-- Filter panel — catalog sources inline + search + toggle filters -->
    <FilterPanel
      v-model="filters.search"
      placeholder="Search scrapers by name, description, or category"
      :debounce-ms="300"
      show-search-icon
      :show-reset="true"
      :has-active-filters="hasActiveFilters"
      :has-advanced-filters="hasAdvancedFilters"
      @search="onSearchInput"
      @reset="resetFilters"
    >
      <template #above>
        <ScraperCatalogSources
          @sources-changed="onSourcesChanged"
        />
      </template>
      <template #below>
        <FilterSortSelect
          v-model="filters.sortBy"
          :options="sortOptions"
          label="Sort by"
          :show-order="true"
          :order="filters.sortOrder"
          @toggle-order="toggleSortOrder"
        />
        <FilterToggleGroup
          label="Data"
          v-model="filters.selectedRichness"
          :options="richnessOptions"
          :multi="true"
        />
      </template>
      <template #advanced>
        <FilterToggleGroup
          label="Category"
          v-model="filters.selectedCategories"
          :options="categoryOptions"
          :multi="true"
        />
        <FilterToggleGroup
          label="Type"
          v-model="filters.selectedTypes"
          :options="typeOptions"
          :multi="true"
        />
      </template>
    </FilterPanel>

    <!-- Section: installed count (badge) + reinstall-all button -->
    <SectionHeading v-if="scrapers.length" title="Installed" :count="installedCount" level="h2">
      <BaseButton
        style="margin-left: auto"
        variant="secondary"
        size="sm"
        :disabled="installedCount === 0 || isRunning || reinstallingAll"
        :loading="reinstallingAll"
        @click="showReinstallConfirm = true"
      >Reinstall All</BaseButton>
    </SectionHeading>

    <div v-if="loading" class="loading">Loading catalog...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="!scrapers.length" class="empty">
      <EmptyState title="No Catalog Sources Configured" message="Add a catalog source to browse installable scraper packages" />
    </div>
    <div v-else-if="!filteredScrapers.length" class="empty">
      <EmptyState title="No scrapers match your filters" message="Try adjusting the filter criteria" />
    </div>
    <div v-else class="catalog-grid">
      <div v-for="s in filteredScrapers" :key="s.id" class="catalog-col">
        <Card class="catalog-card" :class="{ 'catalog-card--installed': s.installed }">
          <div class="catalog-card-body">
            <div class="catalog-card-name-row">
              <div class="catalog-card-name">
                <a v-if="s.homepage" :href="s.homepage" target="_blank" rel="noopener" class="catalog-card-name-link">
                  {{ s.name || s.id }} <AppIcon name="external-link" :size="12" />
                </a>
                <span v-else>{{ s.name || s.id }}</span>
              </div>
              <span v-if="s.installed" class="catalog-menu-wrap" :ref="el => setCatalogMenuRef(s.id, el)">
                <button
                  class="catalog-menu-btn"
                  :class="{ open: openCatalogMenuId === s.id }"
                  title="Scraper actions"
                  @click.stop="openCatalogMenuId = openCatalogMenuId === s.id ? null : s.id"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>
                </button>
                <div v-if="openCatalogMenuId === s.id" class="catalog-menu-dropdown" @click.stop>
                  <button
                    class="catalog-menu-item"
                    :disabled="isRunning"
                    @click="viewSource(s); openCatalogMenuId = null"
                  >Source Code</button>
                  <button
                    class="catalog-menu-item"
                    :disabled="isRunning"
                    @click="reinstallScraper(s); openCatalogMenuId = null"
                  >Reinstall</button>
                  <button
                    class="catalog-menu-item menu-danger"
                    :disabled="isRunning"
                    @click="toggleInstall(s); openCatalogMenuId = null"
                  >Uninstall</button>
                </div>
              </span>
              <button
                v-else
                class="catalog-install-btn"
                :disabled="isRunning || busyId === s.id"
                @click="toggleInstall(s)"
              ><span v-if="busyId === s.id" class="install-spinner"></span>{{ busyId === s.id ? 'Installing...' : 'Install' }}</button>
            </div>
            <div class="catalog-card-desc" v-if="s.description">{{ s.description }}</div>
          </div>
          <div class="catalog-card-tags">
            <StatusBadge v-if="s.dataRichness === 'high'" variant="success" label="High" />
            <StatusBadge v-else-if="s.dataRichness === 'medium'" variant="warning" label="Medium" />
            <StatusBadge v-else-if="s.dataRichness === 'low'" variant="danger" label="Low" />
            <StatusBadge v-else-if="s.dataRichness === 'unknown'" variant="muted" label="Unknown" />
            <span v-for="cat in (Array.isArray(s.category) ? s.category : [s.category || 'other'])" :key="cat" class="tag-chip">{{ cat }}</span>
            <StatusBadge v-if="s.needsBrowser" variant="warning" label="needs Playwright" />
            <span v-for="cap in (s.capabilities || [])" :key="cap" class="tag-chip catalog-cap">{{ cap }}</span>
          </div>
          <div class="catalog-card-footer">
            <span class="catalog-pkg-name">{{ s.npmPackage || '@job-engine-scrapers/scraper-' + s.id }}</span>
            <span v-if="s.version" class="catalog-pkg-version">v{{ s.version }}</span>
            <span v-if="s.installed && s.version && s.installed_version && s.version !== s.installed_version" class="catalog-update-badge">Update available</span>
          </div>
        </Card>
      </div>
    </div>

    <!-- Source Code Viewer Modal -->
    <div v-if="sourceModal.visible" class="source-modal-overlay" @click.self="closeSourceModal">
      <div class="modal modal--large" @click.stop>
        <div class="modal-header">
          <h3>Source: {{ sourceModal.id }}</h3>
          <button class="modal-close" @click="closeSourceModal" aria-label="Close"><AppIcon name="x" :size="14" /></button>
        </div>
        <div class="modal-body source-modal-body">
          <div v-if="sourceModal.loading" class="source-loading">Loading source files...</div>
          <div v-else-if="sourceModal.error" class="source-error">{{ sourceModal.error }}</div>
          <template v-else>
            <div class="source-tabs">
              <button
                v-for="(content, name) in sourceModal.files"
                :key="name"
                class="source-tab-btn"
                :class="{ active: sourceModal.activeTab === name }"
                @click="sourceModal.activeTab = name"
              >{{ name }}</button>
            </div>
            <div class="source-tab-contents">
              <div
                v-for="(content, name) in sourceModal.files"
                :key="name"
                class="source-tab-content"
                :class="{ active: sourceModal.activeTab === name }"
              >
                <pre class="source-code"><code>{{ content }}</code></pre>
              </div>
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <BaseButton variant="secondary" @click="closeSourceModal">Close</BaseButton>
        </div>
      </div>
    </div>

    </div>

    <!-- Confirm Uninstall Modal -->
    <ConfirmModal
      :visible="showConfirm"
      title="Uninstall Scraper"
      :message="`Uninstall &quot;${pendingScraper?.name || pendingScraper?.id || ''}&quot;? The scraper will no longer be available for scraping`"
      confirm-text="Uninstall"
      confirm-variant="soft-red"
      @confirm="confirmUninstall"
      @cancel="cancelUninstall"
    />

    <!-- Confirm Reinstall All Modal -->
    <ConfirmModal
      :visible="showReinstallConfirm"
      title="Reinstall All Scrapers"
      :message="`Reinstall all ${installedCount} installed scrapers? This will uninstall and reinstall each one.`"
      confirm-text="Reinstall All"
      confirm-variant="primary"
      @confirm="confirmReinstallAll"
      @cancel="showReinstallConfirm = false"
    />

    <!-- Reinstall Results Modal -->
    <div v-if="reinstallResults" class="source-modal-overlay" @click.self="reinstallResults = null">
      <div class="modal modal--medium" @click.stop>
        <div class="modal-header">
          <h3>Reinstall Complete</h3>
          <button class="modal-close" @click="reinstallResults = null" aria-label="Close"><AppIcon name="x" :size="14" /></button>
        </div>
        <div class="modal-body">
          <p><strong>{{ reinstallResults.succeeded }}/{{ reinstallResults.total }}</strong> scrapers reinstalled successfully.</p>
          <div v-if="reinstallResults.failed > 0" class="reinstall-errors">
            <p class="reinstall-errors-title">Errors:</p>
            <ul>
              <li v-for="r in reinstallResults.results.filter(r => !r.success)" :key="r.id" class="reinstall-error-item">
                <strong>{{ r.id }}</strong> ({{ r.step }}): {{ r.error }}
              </li>
            </ul>
          </div>
        </div>
        <div class="modal-footer">
          <BaseButton variant="secondary" @click="reinstallResults = null">Close</BaseButton>
        </div>
      </div>
    </div>
</template>
<script setup>
import { ref, computed, reactive, onMounted, onUnmounted } from 'vue'
import { useFetch } from '../../composables/useFetch.js'
import { showToast } from '../../composables/useToast.js'
import { useFilters } from '../../composables/useFilters.js'
import FilterPanel from '../common/FilterPanel.vue'
import FilterToggleGroup from '../common/filters/FilterToggleGroup.vue'
import FilterSortSelect from '../common/filters/FilterSortSelect.vue'
import ScraperCatalogSources from './ScraperCatalogSources.vue'
import EmptyState from '../common/EmptyState.vue'
import BaseButton from '../common/BaseButton.vue'
import SectionHeading from '../common/SectionHeading.vue'
import ConfirmModal from '../common/ConfirmModal.vue'
import Card from '../common/Card.vue'
import AppIcon from '../common/AppIcon.vue'
import StatusBadge from '../common/StatusBadge.vue'

function onCatalogKeydown(e) {
  if (e.key !== 'Escape') return
  if (sourceModal.visible) closeSourceModal()
  else if (reinstallResults.value) reinstallResults.value = null
}
onMounted(() => document.addEventListener('keydown', onCatalogKeydown))
onUnmounted(() => document.removeEventListener('keydown', onCatalogKeydown))

const props = defineProps({
  isRunning: { type: Boolean, default: false },
})
const emitCatalog = defineEmits(['installed', 'uninstalled'])

const scrapers = ref([])
const loading = ref(false)
const error = ref(null)

// Confirm uninstall modal state
const showConfirm = ref(false)
const pendingScraper = ref(null)
const busyId = ref(null)

// Catalog card menu state
const openCatalogMenuId = ref(null)
const catalogMenuRefs = {}

function setCatalogMenuRef(id, el) {
  if (el) catalogMenuRefs[id] = el
  else delete catalogMenuRefs[id]
}

function onClickOutsideCatalogMenu(e) {
  if (!openCatalogMenuId.value) return
  const wrap = catalogMenuRefs[openCatalogMenuId.value]
  if (wrap && !wrap.contains(e.target)) openCatalogMenuId.value = null
}
onMounted(() => document.addEventListener('click', onClickOutsideCatalogMenu))
onUnmounted(() => document.removeEventListener('click', onClickOutsideCatalogMenu))

// Reinstall-all state
const showReinstallConfirm = ref(false)
const reinstallingAll = ref(false)
const reinstallResults = ref(null)

// Multi-select filter definitions — values must match API data (lowercase)
const categoryFilters = ['polish', 'global', 'crypto', 'freelance', 'remote']
const richnessFilters = ['high', 'medium', 'low']
const typeFilters = ['browser', 'api', 'fetch']

const categoryOptions = categoryFilters.map(v => ({ value: v, label: v.charAt(0).toUpperCase() + v.slice(1) }))
const richnessOptions = richnessFilters.map(v => ({ value: v, label: v.charAt(0).toUpperCase() + v.slice(1) }))
const typeOptions = typeFilters.map(v => ({ value: v, label: v === 'api' ? 'API' : v.charAt(0).toUpperCase() + v.slice(1) }))

const { filters, hasActiveFilters, reset } = useFilters({
  search: '',
  selectedCategories: new Set(),
  selectedRichness: new Set(),
  selectedTypes: new Set(),
  sortBy: 'name',
  sortOrder: 'asc',
})

const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'richness', label: 'Data Richness' },
  { value: 'category', label: 'Category' },
  { value: 'installed', label: 'Installed' },
]

const hasAdvancedFilters = computed(() =>
  filters.selectedCategories.size > 0 || filters.selectedTypes.size > 0
)

const filteredScrapers = computed(() => {
  let list = scrapers.value

  // Search
  if (filters.search) {
    const q = filters.search.toLowerCase()
    list = list.filter(s => {
      const name = (s.name || '').toLowerCase()
      const id = (s.id || '').toLowerCase()
      const desc = (s.description || '').toLowerCase()
      const cats = Array.isArray(s.category) ? s.category : [s.category || '']
      return name.includes(q) || id.includes(q) || desc.includes(q) || cats.some(c => c.toLowerCase().includes(q))
    })
  }

  // Category: OR within group — if none selected, show all
  if (filters.selectedCategories.size > 0) {
    list = list.filter(s => {
      if (Array.isArray(s.category)) {
        return s.category.some(cat => filters.selectedCategories.has(cat))
      }
      return filters.selectedCategories.has(s.category)
    })
  }

  // Data richness: OR within group
  if (filters.selectedRichness.size > 0) {
    list = list.filter(s => filters.selectedRichness.has(s.dataRichness))
  }

  // Type: OR within group (matched against capabilities)
  if (filters.selectedTypes.size > 0) {
    list = list.filter(s => (s.capabilities || []).some(cap => filters.selectedTypes.has(cap)))
  }

  // Sort by selected criteria
  const sortBy = filters.sortBy
  const order = filters.sortOrder
  return list.sort((a, b) => {
    let cmp = 0
    if (sortBy === 'richness') {
      const richnessOrder = { high: 0, medium: 1, low: 2, unknown: 3 }
      cmp = (richnessOrder[a.dataRichness] ?? 4) - (richnessOrder[b.dataRichness] ?? 4)
    } else if (sortBy === 'category') {
      const aCat = (Array.isArray(a.category) ? a.category[0] : a.category || '')
      const bCat = (Array.isArray(b.category) ? b.category[0] : b.category || '')
      cmp = aCat.localeCompare(bCat)
    } else if (sortBy === 'installed') {
      cmp = (a.installed ? 0 : 1) - (b.installed ? 0 : 1)
    } else { // name (default)
      const an = (a.name || a.id || '').toLowerCase()
      const bn = (b.name || b.id || '').toLowerCase()
      cmp = an < bn ? -1 : an > bn ? 1 : 0
    }
    return order === 'asc' ? cmp : -cmp
  })
})

function resetFilters() {
  reset()
}

function toggleSortOrder() {
  filters.sortOrder = filters.sortOrder === 'asc' ? 'desc' : 'asc'
}

function onSearchInput() {
  // Search is purely client-side via filteredScrapers computed
}

async function fetchCatalog() {
  loading.value = true; error.value = null
  try {
    const { execute } = useFetch('/api/scrapers/catalog/list')
    const data = await execute()
    scrapers.value = data?.scrapers || data || []
  } catch (e) {
    error.value = e.message
  }
  loading.value = false
}

async function onSourcesChanged() {
  await fetchCatalog()
}

async function reinstallScraper(s) {
  busyId.value = s.id
  try {
    const res = await fetch(`/api/scrapers/catalog/reinstall/${s.id}`, { method: 'POST' })
    if (res.ok) {
      await fetchCatalog()
      emitCatalog('installed', s.id)
      showToast(`${s.name} reinstalled`, 'success')
    } else {
      const err = await res.json()
      showToast(err.detail || 'Reinstall failed', 'error')
    }
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    busyId.value = null
  }
}

async function toggleInstall(s) {
  if (s.installed) {
    pendingScraper.value = s
    showConfirm.value = true
    return
  }
  await doInstall(s)
}

async function doInstall(s) {
  busyId.value = s.id
  try {
    const action = s.installed ? 'uninstall' : 'install'
    const res = await fetch(`/api/scrapers/catalog/${action}/${s.id}`, { method: 'POST' })
    if (res.ok) {
      // Re-fetch catalog from API to ensure UI state is in sync with backend
      await fetchCatalog()
      emitCatalog(action === 'install' ? 'installed' : 'uninstalled', s.id)
      showToast(`${s.name} ${action === 'install' ? 'installed' : 'uninstalled'}`, 'success')
    } else {
      const err = await res.json()
      showToast(err.detail || 'Operation failed', 'error')
    }
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    busyId.value = null
  }
}

function confirmUninstall() {
  showConfirm.value = false
  if (pendingScraper.value) {
    doInstall(pendingScraper.value)
    pendingScraper.value = null
  }
}

function cancelUninstall() {
  showConfirm.value = false
  pendingScraper.value = null
}

const installedCount = computed(() => scrapers.value.filter(s => s.installed).length)
const filteredCount = computed(() => filteredScrapers.value.length)

function confirmReinstallAll() {
  showReinstallConfirm.value = false
  reinstallAll()
}

async function reinstallAll() {
  reinstallingAll.value = true
  reinstallResults.value = null
  try {
    const res = await fetch('/api/scrapers/catalog/reinstall-all', { method: 'POST' })
    const data = await res.json()
    if (res.ok) {
      reinstallResults.value = data
      await fetchCatalog()
      emitCatalog('installed', '__all__')
      showToast(data.message, 'success')
    } else {
      reinstallResults.value = data
      showToast(data.error || 'Reinstall failed', 'error')
    }
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    reinstallingAll.value = false
  }
}

// Source code viewer modal
const sourceModal = reactive({
  visible: false,
  id: '',
  files: {},
  activeTab: null,
  loading: false,
  error: '',
})

async function viewSource(s) {
  sourceModal.id = s.id
  sourceModal.files = {}
  sourceModal.activeTab = null
  sourceModal.error = ''
  sourceModal.loading = true
  sourceModal.visible = true
  try {
    const res = await fetch(`/api/scrapers/catalog/source/${s.id}`)
    if (!res.ok) {
      const err = await res.json()
      sourceModal.error = err.detail || 'Failed to load source'
      sourceModal.loading = false
      return
    }
    const data = await res.json()
    sourceModal.files = data.files || {}
    const fileNames = Object.keys(sourceModal.files)
    if (fileNames.length > 0) {
      sourceModal.activeTab = fileNames[0]
    }
  } catch (e) {
    sourceModal.error = e.message
  }
  sourceModal.loading = false
}

function closeSourceModal() {
  sourceModal.visible = false
}

onMounted(() => fetchCatalog())
defineExpose({ fetchCatalog, filteredCount })
</script>

<style scoped>

.catalog-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }
.catalog-header h3 { font-size: 0.875rem; font-weight: 600; margin: 0; }

/* Catalog grid — compact cards like old template */
.catalog-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  width: 100%;
}
.catalog-col { display: flex; }
.catalog-card {
  display: flex; flex-direction: column; width: 100%;
  transition: box-shadow 0.15s, transform 0.15s;
  padding:0;
}
.catalog-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); transform: translateY(-1px); }
.catalog-card--installed {
  border-color: #22c55e;
  background: #22c55e08;
}
/* Name row with title + menu button */
.catalog-card-name-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 4px;
}
.catalog-card-name {
  font-weight: 600; font-size: 13px; color: var(--color-text, #1e293b); line-height: 1.3; margin-bottom: 6px;
  flex: 1; min-width: 0;
}
.catalog-card-name-link { color: var(--color-text, #1e293b); text-decoration: none; }
.catalog-card-name-link:hover { color: var(--color-primary, #2563eb); }
.catalog-card-arrow { font-size: 11px; opacity: 0.5; margin-left: 1px; }
.catalog-card-name-link:hover .catalog-card-arrow { opacity: 1; color: var(--color-primary, #2563eb); }

/* Direct install button for non-installed scrapers */
.catalog-install-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px; border: none; border-radius: 6px;
  font-size: 11px; font-weight: 600;
  background: #16a34a; color: #fff;
  cursor: pointer; transition: background 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
  margin-top: 1px;
}
.catalog-install-btn:hover {
  background: #15803d;
}
.catalog-install-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* Spinner for install loading state */
.install-spinner {
  display: inline-block;
  width: 12px; height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: install-spin 0.6s linear infinite;
}
@keyframes install-spin {
  to { transform: rotate(360deg); }
}

/* Three-dot menu in the card title */
.catalog-menu-wrap {
  position: relative;
  flex-shrink: 0;
  margin-top: 1px;
}
.catalog-menu-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; padding: 0;
  border: none; border-radius: 4px;
  background: transparent;
  color: var(--color-text-tertiary, #94a3b8);
  cursor: pointer; transition: background 0.15s, color 0.15s;
  opacity: 0.4;
}
.catalog-card:hover .catalog-menu-btn,
.catalog-menu-btn.open {
  opacity: 1;
}
.catalog-menu-btn:hover,
.catalog-menu-btn.open {
  background: var(--color-bg-hover, #e2e8f0);
  color: var(--color-text, #1e293b);
}
.catalog-menu-dropdown {
  position: absolute; top: 100%; right: 0; margin-top: 2px; z-index: 50;
  min-width: 130px;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  padding: 4px;
}
.catalog-menu-item {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 5px 8px;
  border: none; border-radius: 6px;
  background: none;
  font-size: 12px; font-weight: 500;
  color: var(--color-text, #1e293b);
  cursor: pointer; transition: background 0.1s;
  text-align: left;
  box-sizing: border-box;
  white-space: nowrap;
}
.catalog-menu-item:hover:not(:disabled) {
  background: var(--color-bg-hover, #f1f5f9);
}
.catalog-menu-item:disabled {
  opacity: 0.4;
  cursor: default;
}
.catalog-menu-item.menu-danger {
  color: #dc2626;
}
.catalog-menu-item.menu-danger:hover {
  background: rgba(220,38,38,0.08);
}.catalog-card-body { flex: 1; padding: 10px 12px; display: flex; flex-direction: column; }
.catalog-card-desc { font-size: 12px; color: var(--color-text-secondary, #64748b); line-height: 1.4; }

/* Tags row */
.catalog-card-tags {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 0 12px 8px; align-items: center;
}
.tag-chip {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  font-size: 10px; font-weight: 500; background: rgba(37,99,235,0.08); color: #1e40af;
  line-height: 1.4;
}
.catalog-cap { font-size: 10px; padding: 1px 6px; }

/* Footer */
.catalog-card-footer {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px; border-top: 1px solid var(--color-border, #e2e8f0);
  font-size: 11px; color: var(--color-text-secondary, #64748b);
  overflow: hidden; white-space: nowrap; flex-wrap: wrap;
}
.catalog-pkg-name {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: 'SF Mono', 'SFMono-Regular', 'Consolas', monospace; font-size: 10px;
}
.catalog-pkg-version {
  font-size: 10px; color: var(--color-text-secondary, #64748b);
  font-family: 'SF Mono', 'SFMono-Regular', 'Consolas', monospace;
}
.catalog-update-badge {
  display: inline-block; padding: 1px 6px; border-radius: 10px; font-size: 9px;
  font-weight: 600; background: rgba(245,158,11,0.1); color: #b45309; white-space: nowrap;
}
/* Buttons come from the global button system (buttons.css) via BaseButton. */
.loading, .error, .empty { text-align: center; padding: 2rem; color: var(--color-text-secondary, #64748b); }

/* Source Code Viewer Modal */
.source-modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 2000;
  display: flex; align-items: center; justify-content: center;
}
.modal {
  background: var(--color-bg-card, #fff); border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden;
  width: 100%; max-width: 800px; max-height: 80vh; margin: 1rem;
  display: flex; flex-direction: column;
}
.modal--large { max-width: 800px; }
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border, #e2e8f0);
}
.modal-header h3 { font-size: 1rem; font-weight: 600; margin: 0; }
.modal-close { background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--color-text-secondary, #64748b); line-height: 1; }
.modal-close:hover { color: var(--color-text, #1e293b); }
.modal-body { padding: 20px; overflow-y: auto; flex: 1; }
.source-modal-body { display: flex; flex-direction: column; padding: 0; overflow: hidden; }
.source-loading, .source-error { padding: 2rem; text-align: center; font-size: 0.875rem; color: var(--color-text-secondary, #64748b); }
.source-error { color: #991b1b; }
.source-tabs {
  display: flex; border-bottom: 1px solid var(--color-border, #e2e8f0);
  background: #f8fafc; flex-shrink: 0;
}
.source-tab-btn {
  padding: 8px 16px; font-size: 12px; font-weight: 500; border: none;
  background: none; cursor: pointer; color: var(--color-text-secondary, #64748b);
  border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.source-tab-btn:hover { color: var(--color-text, #1e293b); }
.source-tab-btn.active { color: var(--color-primary, #2563eb); border-bottom-color: var(--color-primary, #2563eb); }
.source-tab-contents { flex: 1; overflow: auto; }
.source-tab-content { display: none; padding: 16px; }
.source-tab-content.active { display: block; }
.source-code {
  margin: 0; font-size: 12px; line-height: 1.5; overflow-x: auto;
  font-family: 'SF Mono', 'SFMono-Regular', 'Consolas', monospace;
  color: var(--color-text, #1e293b); background: #f8fafc; border-radius: 6px; padding: 12px;
}
.source-code code { white-space: pre; }
.modal-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 8px;
  padding: 12px 20px; border-top: 1px solid var(--color-border, #e2e8f0);
}
.modal--medium { max-width: 520px; }
.reinstall-errors { margin-top: 12px; }
.reinstall-errors-title { font-weight: 600; margin: 0 0 6px 0; font-size: 0.875rem; color: #991b1b; }
.reinstall-error-item { font-size: 0.8125rem; margin-bottom: 4px; }
/* ── Responsive: small screens ── */
@media (max-width: 640px) {
  .catalog-grid { grid-template-columns: 1fr; gap: 8px; }
  .catalog-card-desc { font-size: 11px; }
  .catalog-card-tags { gap: 2px; }
  .catalog-card-tags .tag { font-size: 9px; padding: 0 4px; }
  .catalog-card-name { font-size: 12px; }
  .catalog-card-footer { padding: 6px 10px; }
  .catalog-menu-dropdown { right: auto; left: 0; }
}
</style>