<template>
  <div v-if="visible" class="modal-backdrop" @click.self="close">
    <div class="modal-overlay">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Run Logs — {{ truncateId(runId, 12) }}</h3>
          <button class="modal-close" @click="close">&times;</button>
        </div>
        <div class="modal-body">
          <LogViewer :run-id="runId" />
        </div>
        <div class="modal-footer">
          <BaseButton variant="secondary" @click="close">Close</BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import LogViewer from './LogViewer.vue'
import BaseButton from '../common/BaseButton.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  runId: { type: String, required: true },
})
const emit = defineEmits(['close'])

function close() {
  emit('close')
}

function truncateId(id, max = 8) {
  if (!id) return '—'
  if (id.length <= max) return id
  return id.substring(0, max) + '…'
}

function onKeydown(e) {
  if (e.key === 'Escape' && props.visible) close()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.modal-overlay {
  position: relative; width: 100%; max-width: 800px; margin: 1rem;
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
.modal-body {
  padding: 0;
  max-height: 70vh;
  overflow-y: auto;
}
.modal-footer {
  display: flex; justify-content: flex-end; gap: 0.5rem;
  padding: 0.75rem 1.25rem; border-top: 1px solid var(--color-border, #e2e8f0);
}
</style>