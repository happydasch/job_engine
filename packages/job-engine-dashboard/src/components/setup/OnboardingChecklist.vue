<template>
  <div v-if="visible" class="onboarding-checklist">
    <div class="onboarding-header">
      <h3>Getting Started</h3>
      <button class="onboarding-dismiss" @click="dismiss" title="Dismiss" aria-label="Dismiss"><AppIcon name="x" :size="14" /></button>
    </div>
    <p class="onboarding-subtitle">Complete these steps to get the most out of your job search engine.</p>
    <div class="steps-list">
      <div
        v-for="step in steps"
        :key="step.id"
        class="step-row"
        :class="{ 'step-done': step.done, 'step-available': !step.done && steps[indexOf(step)]?.id === firstIncompleteId }"
      >
        <span class="step-icon"><AppIcon :name="step.done ? 'check' : 'circle'" :size="13" /></span>
        <span class="step-label">{{ step.label }}</span>
        <router-link v-if="!step.done && !isSidebarAction(step.action)" :to="step.action" class="step-action">Go</router-link>
        <button v-else-if="!step.done && isSidebarAction(step.action)" class="step-action step-action-btn" @click="handleSidebarAction(step.action)">Go</button>
        <span v-else class="step-done-label">Done</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import AppIcon from '../common/AppIcon.vue'

const visible = ref(false)
const loading = ref(true)
const steps = ref([])

const openSidebar = inject('openSidebar', null)

function isSidebarAction(action) {
  return typeof action === 'string' && action.startsWith('sidebar:')
}

function handleSidebarAction(action) {
  const panel = action.replace('sidebar:', '')
  if (openSidebar) {
    openSidebar(panel)
  }
}

const firstIncompleteId = computed(() => {
  const s = steps.value.find(s => !s.done)
  return s ? s.id : null
})

function indexOf(step) {
  return steps.value.indexOf(step)
}

async function dismiss() {
  visible.value = false
  try {
    await fetch('/api/app-settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section: 'onboarding', values: { dismissed: true } }),
    })
  } catch { /* ignore */ }
}

async function loadStatus() {
  try {
    // Load dismissed state from settings
    const settingsRes = await fetch('/api/app-settings')
    let alreadyDismissed = false
    if (settingsRes.ok) {
      const data = await settingsRes.json()
      alreadyDismissed = !!data?.onboarding?.dismissed
      if (!alreadyDismissed) {
        visible.value = true
      }
    }
    loading.value = false

    // Load setup status (steps) regardless
    const res = await fetch('/api/setup/status')
    if (res.ok) {
      const data = await res.json()
      if (data?.steps) {
        steps.value = data.steps
      }
    }

    // All steps already complete (e.g. an existing setup) — don't nag with
    // a permanent "Getting Started" banner the user never explicitly dismissed.
    if (!alreadyDismissed && steps.value.length && steps.value.every(s => s.done)) {
      await dismiss()
    }
  } catch { /* ignore */ }
}

onMounted(loadStatus)
</script>

<style scoped>
.onboarding-checklist {
  background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
  border: 1px solid #bbf7d0;
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}
.onboarding-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.onboarding-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #166534;
}
.onboarding-dismiss {
  background: none;
  border: none;
  font-size: 1.4rem;
  cursor: pointer;
  color: #64748b;
  line-height: 1;
  padding: 0.125rem 0.25rem;
}
.onboarding-dismiss:hover {
  color: #1e293b;
}
.onboarding-subtitle {
  margin: 0.25rem 0 0.75rem;
  font-size: 0.8125rem;
  color: #4b5563;
}
.steps-list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.step-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.5rem;
  border-radius: 6px;
  font-size: 0.8125rem;
}
.step-row.step-available {
  background: rgba(22, 163, 74, 0.08);
  font-weight: 500;
}
.step-icon {
  font-size: 0.875rem;
  flex-shrink: 0;
}
.step-label {
  flex: 1;
  color: #1e293b;
}
.step-done .step-label {
  color: #6b7280;
  text-decoration: line-through;
}
.step-action {
  font-size: 0.75rem;
  font-weight: 500;
  color: #2563eb;
  text-decoration: none;
  padding: 0.2rem 0.5rem;
  border: 1px solid #2563eb;
  border-radius: 6px;
  transition: all 0.15s;
}
.step-action:hover {
  background: #2563eb;
  color: #fff;
}
.step-action-btn {
  cursor: pointer;
  font-family: inherit;
  background: transparent;
}
.step-action-btn:hover {
  background: #2563eb;
  color: #fff;
}
.step-done-label {
  font-size: 0.75rem;
  color: #16a34a;
  font-weight: 500;
}
</style>