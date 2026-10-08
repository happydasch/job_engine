<template>
  <div class="toast-container" aria-live="polite" aria-atomic="false">
    <transition-group name="toast">
      <div
        v-for="n in notifications"
        :key="n.id"
        class="toast"
        :class="n.type"
        :role="n.type === 'error' ? 'alert' : 'status'"
        tabindex="0"
        @click="dismiss(n.id)"
        @keydown.enter.prevent="dismiss(n.id)"
        @keydown.space.prevent="dismiss(n.id)"
        @keydown.escape.prevent="dismiss(n.id)"
      >
        {{ n.message }}
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { useNotifications } from '../../composables/useToast'

const { notifications, dismiss } = useNotifications()
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  pointer-events: none;
}
.toast {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  cursor: pointer;
  pointer-events: auto;
  max-width: 360px;
}
.success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
.error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.info { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
.warning { background: #fefce8; color: #854d0e; border: 1px solid #fde68a; }
.toast-enter-active { transition: all 0.3s ease; }
.toast-leave-active { transition: all 0.2s ease; }
.toast-enter-from { opacity: 0; transform: translateX(30px); }
.toast-leave-to { opacity: 0; transform: translateX(30px); }
</style>