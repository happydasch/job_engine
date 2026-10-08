<template>
  <FilterPanel
    v-model="f.q"
    placeholder="Search jobs by title, skill, company, location…"
    :debounce-ms="0"
    show-search-icon
    :show-reset="true"
    :has-active-filters="props.hasActiveFilters"
    :has-advanced-filters="hasAdvancedFilters"
    @search="emitUpdate"
    @reset="clearFilters"
  >
    <template #below>
        <FilterSortSelect
          v-model="f.sort_by"
          label="Sort by"
          :options="sortOptions"
          :show-order="true"
          :order="f.sort_order"
          @update:modelValue="emitUpdate"
          @toggle-order="toggleSortOrder"
        />
        <div class="score-toggle-group">
          <FilterLabel>Min score</FilterLabel>
          <div class="score-buttons">
            <button
              v-for="btn in scoreButtons"
              :key="btn.value"
              :class="['score-btn', { active: f.min_score === btn.value }]"
              :style="f.min_score === btn.value ? { background: btn.color, borderColor: btn.color, color: '#fff' } : {}"
              @click="setMinScore(btn.value)"
            >{{ btn.label }}</button>
          </div>
        </div>
      </template>

      <template #advanced>
        <div class="filter-group">
          <label>Platform</label>
          <select v-model="f.platform" @change="emitUpdate">
            <option value="">All Platforms</option>
            <option v-for="p in platforms" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>
        <div class="filter-group">
          <label>Remote</label>
          <select v-model="f.remote" @change="emitUpdate">
            <option value="">All</option>
            <option value="true">Remote Only</option>
            <option value="false">On-site Only</option>
          </select>
        </div>
        <div class="filter-group">
          <label>Skill</label>
          <select v-model="f.skill" @change="emitUpdate">
            <option value="">All Skills</option>
            <option v-for="s in skills" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div class="filter-group">
          <label>Location</label>
          <select v-model="f.location" @change="emitUpdate">
            <option value="">All Locations</option>
            <option v-for="loc in locations" :key="loc" :value="loc">{{ loc }}</option>
          </select>
        </div>
        <div class="filter-group">
          <label>Category</label>
          <select v-model="f.category" @change="emitUpdate">
            <option value="">All Categories</option>
            <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
          </select>
        </div>
        <FilterToggleGroup
          label="Experience"
          :options="experienceOptions"
          :multi="true"
          :model-value="selectedExperience"
          @update:model-value="onExperienceUpdate"
        />
        <FilterToggleGroup
          label="Contract"
          :options="contractOptions"
          :multi="true"
          :model-value="selectedContract"
          @update:model-value="onContractUpdate"
        />
        <div class="filter-group-toggles">
          <label class="toggle-label">
            <input type="checkbox" v-model="f.show_hidden" @change="emitUpdate" />
            <span class="toggle-switch"></span>
            Show hidden
          </label>
          <label class="toggle-label">
            <input type="checkbox" v-model="f.hidden_only" @change="emitUpdate" />
            <span class="toggle-switch"></span>
            Hidden only
          </label>
          <label class="toggle-label">
            <input type="checkbox" v-model="f.show_favorites" @change="emitUpdate" />
            <span class="toggle-switch"></span>
            Favorites only
          </label>
          <label class="toggle-label">
            <input type="checkbox" v-model="f.show_applied" @change="emitUpdate" />
            <span class="toggle-switch"></span>
            Applied only
          </label>
          <label class="toggle-label">
            <input type="checkbox" v-model="f.show_enriched" @change="emitUpdate" />
            <span class="toggle-switch"></span>
            Enriched only
          </label>
        </div>
      </template>
    </FilterPanel>
</template>

<script setup>
import { reactive, computed, watch } from 'vue'
import { getExperienceLabel, getContractLabel } from '../../constants/enums.js'
import FilterPanel from '../common/FilterPanel.vue'
import FilterSortSelect from '../common/filters/FilterSortSelect.vue'
import FilterToggleGroup from '../common/filters/FilterToggleGroup.vue'
import FilterLabel from '../common/FilterLabel.vue'

const props = defineProps({
  filters: { type: Object, required: true },
  platforms: { type: Array, default: () => [] },
  skills: { type: Array, default: () => [] },
  locations: { type: Array, default: () => [] },
  experienceLevels: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  contractTypes: { type: Array, default: () => [] },
  hasActiveFilters: { type: Boolean, default: false },
})

const emit = defineEmits(['update'])

// Local working copy — avoids mutating the prop directly
const f = reactive({ ...props.filters })

// Sync from prop when it changes externally (e.g. URL navigation back/forward)
watch(() => props.filters, (val) => {
  Object.assign(f, val)
}, { deep: true })

const hasAdvancedFilters = computed(() => {
  return !!(f.platform || f.remote || f.skill || f.location || f.experience_level || f.category || f.contract_type || f.show_hidden || f.hidden_only || f.show_favorites || f.show_applied || f.show_enriched)
})

const sortOptions = [
  { value: 'match_score', label: 'Match' },
  { value: 'salary_max', label: 'Salary' },
  { value: 'discovered_at', label: 'Newest' },
  { value: 'updated_at', label: 'Updated' },
  { value: 'favorite', label: 'Favs First' },
  { value: 'application', label: 'Applied First' },
]

const scoreButtons = [
  { value: 0, label: 'All', color: 'var(--text-secondary)' },
  { value: 25, label: '25+', color: 'var(--score-med)' },
  { value: 50, label: '50+', color: 'var(--score-high)' },
  { value: 75, label: '75+', color: 'var(--score-top)' },
]

// ── Experience multi-select toggle ─────────────────────────────────────────

const experienceOptions = computed(() => {
  const seen = new Set()
  return props.experienceLevels
    .map(lvl => ({ value: lvl, label: getExperienceLabel(lvl) }))
    .filter(o => { const dup = seen.has(o.label); seen.add(o.label); return !dup })
})

const selectedExperience = computed({
  get: () => {
    if (!f.experience_level) return new Set()
    return new Set(f.experience_level.split(',').map(s => s.trim()).filter(Boolean))
  },
  set: (set) => {
    f.experience_level = [...set].join(',')
    emitUpdate()
  },
})

function onExperienceUpdate(set) {
  selectedExperience.value = set
}

// ── Contract multi-select toggle ───────────────────────────────────────────
const contractOptions = computed(() =>
  props.contractTypes.map(ct => ({ value: ct, label: getContractLabel(ct) }))
)

const selectedContract = computed({
  get: () => {
    if (!f.contract_type) return new Set()
    return new Set(f.contract_type.split(',').map(s => s.trim()).filter(Boolean))
  },
  set: (set) => {
    f.contract_type = [...set].join(',')
    emitUpdate()
  },
})

function onContractUpdate(set) {
  selectedContract.value = set
}

function setMinScore(val) {
  f.min_score = val
  emitUpdate()
}

function emitUpdate() { emit('update', { ...f }) }

function toggleSortOrder() {
  f.sort_order = f.sort_order === 'asc' ? 'desc' : 'asc'
  emit('update', { ...f })
}

function clearFilters() {
  f.q = ''
  f.sort_by = 'match_score'
  f.sort_order = 'desc'
  f.min_score = 0
  f.platform = ''
  f.remote = ''
  f.skill = ''
  f.location = ''
  f.experience_level = ''
  f.category = ''
  f.contract_type = ''
  f.show_hidden = false
  f.hidden_only = false
  f.show_favorites = false
  f.show_applied = false
  f.show_enriched = false
  f.page = 1
  emit('update', { ...f })
}
</script>

<style scoped>
/* Filter group — label + select inline */
.filter-group {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
}
.filter-group label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.4px;
  white-space: nowrap;
}
.filter-group select,
.filter-group input {
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 5px;
  font-size: 11px;
  background: var(--surface);
  color: var(--text);
  min-height: 26px;
  min-width: 0;
  max-width: 100%;
  width: auto;
}
.filter-group select:focus,
.filter-group input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--focus-ring);
}

/* Toggle group — inline checkbox toggles */
.filter-group-toggles {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
}

/* Toggle switch */
.toggle-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text);
  cursor: pointer;
  user-select: none;
}
.toggle-label input { display: none; }
.toggle-switch {
  width: 26px;
  height: 14px;
  border-radius: 7px;
  background: #cbd5e1;
  position: relative;
  transition: background 0.2s;
  flex-shrink: 0;
}
.toggle-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 10px;
  height: 10px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s;
}
.toggle-label input:checked + .toggle-switch {
  background: var(--primary);
}
.toggle-label input:checked + .toggle-switch::after {
  left: auto;
  right: 2px;
  transform: none;
}

/* Score toggle buttons — segmented pill style */
.score-toggle-group {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.score-buttons {
  display: inline-flex;
  gap: 0;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border);
}
.score-btn {
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 500;
  border: none;
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
  border-right: 1px solid var(--border);
  line-height: 1.4;
}
.score-btn:last-child {
  border-right: none;
}
.score-btn:hover:not(.active) {
  background: var(--bg-hover, #f1f5f9);
  color: var(--text);
}
.score-btn.active {
  color: #fff;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.15);
}
</style>
