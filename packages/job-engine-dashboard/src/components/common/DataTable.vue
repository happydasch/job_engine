<template>
  <div>
    <div v-if="loading" class="loading-state">
      <slot name="loading"><span>Loading...</span></slot>
    </div>
    <div v-else-if="error" class="error-state">
      <slot name="error">{{ error }}</slot>
    </div>
    <div v-else-if="!rows.length">
      <slot name="empty">
        <EmptyState :title="emptyTitle" :message="emptyMessage">
          <template #icon>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
          </template>
        </EmptyState>
      </slot>
    </div>
    <div v-else class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th v-if="expandable" class="th-expand"></th>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="[
                col.align === 'right' ? 'th-right' : '',
                col.nowrap ? 'th-nowrap' : '',
              ]"
              :style="col.width ? `width:${col.width}` : ''"
            >
              <span v-if="col.label">{{ col.label }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(row, rowIdx) in rows" :key="rowKey ? row[rowKey] : rowIdx">
            <tr
              :class="[
                rowClass ? rowClass(row, rowIdx) : '',
                expandable ? 'tr-expandable' : '',
              ]"
            >
              <td v-if="expandable" class="td-expand">
                <button
                  class="expand-btn"
                  @click="$emit('toggle-expand', row)"
                  :title="isExpanded(row) ? 'Collapse details' : 'Expand details'"
                >
                  <svg
                    width="14" height="14" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" stroke-width="2" stroke-linecap="round"
                    :class="{ 'rotate-90': isExpanded(row) }"
                  >
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
              </td>
              <td
                v-for="col in columns"
                :key="col.key"
                :class="[
                  col.class || '',
                  col.align === 'right' ? 'td-right' : '',
                  col.nowrap ? 'td-nowrap' : '',
                ]"
              >
                <slot :name="`cell-${col.key}`" :row="row" :value="resolveValue(row, col.key)">
                  <span v-if="resolveValue(row, col.key) != null">{{ resolveValue(row, col.key) }}</span>
                  <span v-else class="td-null">&mdash;</span>
                </slot>
              </td>
            </tr>
            <tr v-if="expandable && isExpanded(row)" class="tr-expanded">
              <td :colspan="columns.length + 1" class="td-expanded-content">
                <slot name="expanded-row" :row="row">{{ row }}</slot>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import EmptyState from './EmptyState.vue'

const props = defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  rowKey: { type: String, default: '' },
  rowClass: { type: Function, default: null },
  emptyTitle: { type: String, default: 'No data' },
  emptyMessage: { type: String, default: '' },
  expandable: { type: Boolean, default: false },
  expandedRows: { type: Set, default: () => new Set() },
})

defineEmits(['toggle-expand'])

function resolveValue(row, key) {
  if (!row || !key) return null
  // Support dot-notation like "job_title"
  if (key.includes('.')) {
    return key.split('.').reduce((o, k) => (o && o[k] !== undefined ? o[k] : null), row)
  }
  const v = row[key]
  return v !== undefined && v !== null ? v : null
}

function isExpanded(row) {
  const key = props.rowKey ? row[props.rowKey] : row.id
  return props.expandedRows.has(key)
}
</script>

<style scoped>
.loading-state,
.error-state {
  padding: 2rem;
  text-align: center;
  color: var(--color-text-secondary, #64748b);
}
.error-state { color: #991b1b; }

.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 8px;
  border-collapse: collapse;
}

.data-table th {
  padding: 12px 16px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary, #64748b);
  border-bottom: 2px solid var(--border, #e2e8f0);
  white-space: nowrap;
}

.data-table th.th-right { text-align: right; }
.data-table th.th-nowrap { white-space: nowrap; }

.data-table td {
  padding: 12px 16px;
  font-size: 13px;
  border-bottom: 1px solid var(--border, #e2e8f0);
  vertical-align: middle;
}

.data-table tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:hover td {
  background: var(--bg, #f8f9fa);
}

.data-table td.td-right { text-align: right; }
.data-table td.td-nowrap { white-space: nowrap; }
.data-table td .td-null { color: var(--text-secondary, #64748b); }
.data-table th.th-expand { width: 40px; padding: 8px; }
.data-table td.td-expand { width: 40px; padding: 8px; text-align: center; vertical-align: middle; }
.data-table tr.tr-expandable { cursor: default; }
.data-table tr.tr-expanded td { padding: 0; }
.data-table tr.tr-expanded:hover td { background: transparent; }
.data-table td.td-expanded-content { padding: 0; }
.expand-btn {
  background: none; border: none; cursor: pointer; padding: 4px;
  color: var(--text-secondary, #64748b); display: inline-flex;
  align-items: center; justify-content: center; border-radius: 4px;
}
.expand-btn:hover { background: var(--bg, #f1f5f9); color: var(--text, #1e293b); }
.rotate-90 { transform: rotate(90deg); transition: transform 0.15s; }
</style>
