<template>
  <Teleport to="body">
    <div v-if="visible" class="base-modal-backdrop" @click.self="onBackdrop">
      <div
        ref="dialogRef"
        class="base-modal"
        :class="`base-modal--${size}`"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <div class="base-modal-header">
          <h3 :id="titleId">{{ title }}</h3>
          <button type="button" class="base-modal-close" aria-label="Close" @click="$emit('close')">
            <AppIcon name="x" :size="14" />
          </button>
        </div>
        <div class="base-modal-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="base-modal-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
/**
 * BaseModal — generic modal with proper dialog semantics.
 *
 * Handles: Escape key, backdrop click (disable with :close-on-backdrop="false"),
 * focus-on-open, and focus return on close. ConfirmModal stays the
 * confirm-specific variant built on top of the same patterns.
 */
import { ref, watch, onUnmounted } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, required: true },
  size: { type: String, default: 'medium' }, // small | medium | large
  closeOnBackdrop: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])

const dialogRef = ref(null)
const titleId = `modal-title-${Math.random().toString(36).slice(2, 9)}`
let previousFocus = null

function onBackdrop() {
  if (props.closeOnBackdrop) emit('close')
}

function onKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    emit('close')
  }
}

watch(() => props.visible, async (v) => {
  if (v) {
    previousFocus = document.activeElement
    document.addEventListener('keydown', onKeydown)
    // Focus the dialog for keyboard/screen-reader users
    requestAnimationFrame(() => dialogRef.value?.focus())
  } else {
    document.removeEventListener('keydown', onKeydown)
    if (previousFocus && document.contains(previousFocus)) {
      previousFocus.focus()
    }
    previousFocus = null
  }
})

onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.base-modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.base-modal {
  background: var(--color-bg-card, #fff); border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden;
  width: 100%; margin: 1rem;
  display: flex; flex-direction: column;
  max-height: calc(100vh - 2rem);
  outline: none;
}
.base-modal--small { max-width: 360px; }
.base-modal--medium { max-width: 560px; }
.base-modal--large { max-width: 860px; }
.base-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border, #e2e8f0);
}
.base-modal-header h3 { font-size: 1rem; font-weight: 600; margin: 0; }
.base-modal-close {
  display: inline-flex; align-items: center; justify-content: center;
  background: none; border: none; cursor: pointer;
  color: var(--color-text-secondary, #64748b); line-height: 1; padding: 2px;
}
.base-modal-close:hover { color: var(--color-text, #1e293b); }
.base-modal-body { padding: 1.25rem; overflow-y: auto; }
.base-modal-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 0.5rem;
  padding: 0.75rem 1.25rem; border-top: 1px solid var(--color-border, #e2e8f0);
}
</style>
