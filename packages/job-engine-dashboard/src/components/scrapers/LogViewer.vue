<template>
  <div class="log-viewer">
    <div class="log-viewer-header">
      <span class="log-viewer-title">Logs — run {{ truncateId(runId, 12) }}</span>
      <span v-if="loading" class="log-viewer-loading">loading…</span>
    </div>

    <div v-if="loadError" class="log-viewer-error">{{ loadError }}</div>

    <template v-else-if="data">
      <div v-if="data.issues && data.issues.length" class="issues-list">
        <div class="issues-list-title">Issues ({{ data.issues.length }})</div>
        <div v-for="(issue, i) in data.issues" :key="i" class="issue-row" :class="'issue-' + issue.severity">
          <span class="issue-severity">{{ issue.severity }}</span>
          <span v-if="issue.source" class="issue-source">{{ issue.source }}</span>
          <span class="issue-message">{{ issue.message }}</span>
        </div>
      </div>

      <div class="log-lines" ref="logBox">
        <div v-if="!data.lines.length" class="log-empty">No log lines recorded</div>
        <div v-for="(entry, i) in data.lines" :key="i" class="log-line" :class="'stream-' + entry.stream">
          <span class="log-ts">{{ formatDateTime(entry.ts) }}</span>
          <span class="log-text">{{ entry.line }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'

const props = defineProps({
  runId: { type: String, required: true },
})

const data = ref(null)
const loading = ref(false)
const loadError = ref('')
const logBox = ref(null)
let tailTimer = null

import { useDateTime } from '../../composables/useDateTime'

const { formatDateTime } = useDateTime()

function truncateId(id, max = 8) {
  if (!id) return '—'
  if (id.length <= max) return id
  return id.substring(0, max) + '…'
}

function scrollToBottom() {
  nextTick(() => {
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  })
}

function stopTailing() {
  if (tailTimer) {
    clearInterval(tailTimer)
    tailTimer = null
  }
}

async function fetchLogs(offset = 0) {
  const res = await fetch(`/api/scrape/logs/${props.runId}?offset=${offset}`)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail || `Failed to load logs (HTTP ${res.status})`)
  }
  return res.json()
}

async function load() {
  stopTailing()
  data.value = null
  loadError.value = ''
  loading.value = true
  try {
    const first = await fetchLogs()
    data.value = first
    scrollToBottom()
    if (first.live) {
      tailTimer = setInterval(async () => {
        try {
          const next = await fetchLogs(data.value.next_offset)
          data.value = { ...next, lines: [...data.value.lines, ...next.lines] }
          if (next.lines.length) scrollToBottom()
          if (!next.live) stopTailing()
        } catch (e) {
          loadError.value = e.message
          stopTailing()
        }
      }, 2000)
    }
  } catch (e) {
    loadError.value = e.message
  }
  loading.value = false
}

watch(() => props.runId, load)
onMounted(load)
onUnmounted(stopTailing)
</script>

<style scoped>
.log-viewer {
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
  overflow: hidden;
}
.log-viewer-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg-hover, #f8fafc);
  border-bottom: 1px solid var(--color-border, #e2e8f0);
}
.log-viewer-title { font-size: 12px; font-weight: 600; font-family: monospace; }
.log-viewer-loading { font-size: 11px; color: var(--color-text-secondary, #64748b); }
.log-viewer-error { padding: 12px; font-size: 12px; color: #991b1b; }

.issues-list { padding: 8px 12px; border-bottom: 1px solid var(--color-border, #e2e8f0); }
.issues-list-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; color: var(--color-text-secondary, #64748b); margin-bottom: 4px; }
.issue-row { display: flex; gap: 8px; padding: 2px 0; font-size: 12px; align-items: baseline; }
.issue-severity { font-size: 10px; font-weight: 700; text-transform: uppercase; flex-shrink: 0; }
.issue-error .issue-severity { color: #dc2626; }
.issue-warning .issue-severity { color: #d97706; }
.issue-source { font-family: monospace; font-size: 11px; color: var(--color-text-secondary, #64748b); flex-shrink: 0; }
.issue-message { color: var(--color-text, #1e293b); word-break: break-word; }

.log-lines {
  max-height: 320px;
  overflow-y: auto;
  padding: 8px 12px;
  font-family: monospace;
  font-size: 11px;
  line-height: 1.5;
  background: var(--color-bg, #ffffff);
}
.log-empty { color: var(--color-text-secondary, #94a3b8); }
.log-line { display: flex; gap: 8px; white-space: pre-wrap; word-break: break-all; }
.log-ts { color: var(--color-text-secondary, #94a3b8); flex-shrink: 0; }
.stream-stderr .log-text { color: #b45309; }
.stream-system .log-text { color: #2563eb; }
</style>
