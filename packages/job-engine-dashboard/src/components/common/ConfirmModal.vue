<template>
  <div v-if="visible" class="confirm-backdrop" @click.self="onCancel">
    <div class="confirm-overlay">
      <div
        ref="dialogRef"
        class="confirm-content"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <div class="confirm-header">
          <h3 :id="titleId">{{ title }}</h3>
          <button class="confirm-close" aria-label="Close" @click="onCancel"><AppIcon name="x" :size="14" /></button>
        </div>
        <div class="confirm-body">
          <p>{{ message }}</p>
          <slot name="message" />
        </div>
        <div class="confirm-footer">
          <BaseButton variant="secondary" @click="onCancel" :disabled="disabled">
            {{ cancelText }}
          </BaseButton>
          <BaseButton :variant="confirmVariant" @click="onConfirm" :disabled="disabled">
            {{ disabled ? confirmingText : confirmText }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import BaseButton from './BaseButton.vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: 'Confirm' },
  message: { type: String, default: 'Are you sure?' },
  confirmText: { type: String, default: 'Confirm' },
  confirmingText: { type: String, default: 'Processing...' },
  cancelText: { type: String, default: 'Cancel' },
  confirmVariant: { type: String, default: 'danger' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'cancel'])

const dialogRef = ref(null)
const titleId = `confirm-title-${Math.random().toString(36).slice(2, 9)}`
let previousFocus = null

function onConfirm() {
  emit('confirm')
}

function onCancel() {
  emit('cancel')
}

function onKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    onCancel()
  }
}

watch(() => props.visible, (v) => {
  if (v) {
    previousFocus = document.activeElement
    requestAnimationFrame(() => dialogRef.value?.focus())
  } else if (previousFocus && document.contains(previousFocus)) {
    previousFocus.focus()
    previousFocus = null
  }
})

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.confirm-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.confirm-overlay {
  position: relative; width: 100%; max-width: 420px; margin: 1rem;
}
.confirm-content {
  background: var(--color-bg-card, #fff); border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden;
}
.confirm-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border, #e2e8f0);
}
.confirm-header h3 { font-size: 1rem; font-weight: 600; margin: 0; }
.confirm-close {
  display: inline-flex; align-items: center; justify-content: center;
  background: none; border: none; cursor: pointer; padding: 2px;
  color: var(--color-text-secondary, #64748b); line-height: 1;
}
.confirm-close:hover { color: var(--color-text, #1e293b); }
.confirm-body { padding: 1.25rem; }
.confirm-body p { font-size: 0.875rem; color: var(--color-text, #1e293b); margin: 0; line-height: 1.5; }
.confirm-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 0.5rem;
  padding: 0.75rem 1.25rem; border-top: 1px solid var(--color-border, #e2e8f0);
}
</style>