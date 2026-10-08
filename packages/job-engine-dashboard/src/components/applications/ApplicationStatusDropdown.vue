<template>
  <span class="app-status-dropdown" ref="containerRef">
    <!-- Trigger badge / default slot -->
    <slot
      name="trigger"
      :status="status"
      :clickable="!isTerminal"
      :toggle="toggleDropdown"
    >
      <StatusBadge
        :status="status"
        :clickable="!!appId"
        class="status-trigger"
        :class="{ 'status-trigger--active': isOpen }"
        @click="toggleDropdown"
      />
    </slot>

    <!-- Popup menu — teleported to body for fixed positioning -->
    <Teleport to="body">
      <div
        v-if="isOpen"
        class="status-popup-fixed"
        :style="popupStyle"
        ref="popupRef"
        @click.stop
      >
        <!-- No app → show Apply action -->
        <template v-if="!appId">
          <button class="dropdown-item" @click="handleApply">
            Apply now
          </button>
        </template>

        <!-- Non-terminal transitions -->
        <template v-else-if="!isTerminal">
          <button
            v-for="t in transitions"
            :key="t"
            class="dropdown-item"
            @click="handleTransition(t)"
          >
            {{ t.charAt(0).toUpperCase() + t.slice(1) }}
          </button>
        </template>

        <!-- Terminal status → reopen -->
        <button
          v-if="isTerminal && appId"
          class="dropdown-item"
          @click="handleReopen"
        >
          Reopen
        </button>

        <!-- Delete (always available when app exists) -->
        <div v-if="appId" class="dropdown-divider" />
        <button
          v-if="appId"
          class="dropdown-item dropdown-item--danger"
          @click="handleDelete"
        >
          Delete
        </button>
      </div>
    </Teleport>
  </span>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import StatusBadge from '../common/StatusBadge.vue'

const props = defineProps({
  status: { type: String, required: true },
  appId: { type: [Number, String], default: null },
  jobExternalId: { type: String, default: null },
  transitions: { type: Array, default: () => [] },
})

const emit = defineEmits(['transition', 'reopen', 'delete', 'apply'])

// No further transitions possible (e.g. rejected/withdrawn) → show "Reopen" instead.
// Note "accepted" is NOT terminal here: it can still transition to "withdrawn".
const isTerminal = computed(() => props.transitions.length === 0)

// Dropdown state
const isOpen = ref(false)
const popupStyle = ref({})
const containerRef = ref(null)
const popupRef = ref(null)

function toggleDropdown() {
  if (isOpen.value) {
    closeDropdown()
  } else {
    openDropdown()
  }
}

function openDropdown() {
  if (!containerRef.value) return
  const el = containerRef.value
  const rect = el.getBoundingClientRect()
  const vw = document.documentElement.clientWidth
  const vh = document.documentElement.clientHeight
  const gap = 4
  const margin = 4

  // Phase 1: show the popup right away, positioned below the trigger + left-aligned
  isOpen.value = true
  popupStyle.value = {
    position: 'fixed',
    top: (rect.bottom + gap) + 'px',
    left: rect.left + 'px',
    right: 'auto',
    bottom: 'auto',
    zIndex: 1000,
  }

  // Phase 2: after Vue renders the popup, measure its actual size and
  // reposition so it stays within the viewport (no hardcoded guesses).
  nextTick(() => {
    if (!popupRef.value) return
    const pr = popupRef.value.getBoundingClientRect()
    const ph = pr.height
    const pw = pr.width

    // --- Vertical ---
    let top = rect.bottom + gap
    const bottomOverflow = top + ph > vh - margin
    if (bottomOverflow) {
      const aboveTop = rect.top - gap - ph
      top = aboveTop >= margin ? aboveTop : Math.max(margin, vh - ph - margin)
    }

    // --- Horizontal ---
    // Prefer left-aligned (popup right edge ≤ viewport right edge).
    // Fall back to right-aligned (popup left edge ≥ margin).
    // Last resort: clamp within viewport margins.
    let left = rect.left
    if (left + pw > vw - margin) {
      const rightAligned = rect.right - pw
      const rightAlignedOk = rightAligned >= margin && rightAligned + pw <= vw - margin
      if (rightAlignedOk) {
        left = rightAligned
      } else {
        left = Math.max(margin, vw - pw - margin)
      }
    }
    if (left < margin) {
      left = margin
    }

    popupStyle.value = {
      position: 'fixed',
      top: top + 'px',
      left: left + 'px',
      right: 'auto',
      bottom: 'auto',
      zIndex: 1000,
    }
  })
}

function closeDropdown() {
  isOpen.value = false
  popupStyle.value = {}
}

function handleTransition(newStatus) {
  if (!props.appId) return
  emit('transition', { appId: props.appId, newStatus })
  closeDropdown()
}

function handleReopen() {
  if (!props.appId) return
  emit('reopen', props.appId)
  closeDropdown()
}

function handleDelete() {
  if (!props.appId) return
  emit('delete', props.appId)
  closeDropdown()
}

function handleApply() {
  if (props.jobExternalId) {
    emit('apply', props.jobExternalId)
  }
  closeDropdown()
}

// Outside click handler
function onDocumentClick(event) {
  if (!isOpen.value) return
  const isInsideContainer = containerRef.value?.contains(event.target)
  const isInsidePopup = popupRef.value?.contains(event.target)
  if (!isInsideContainer && !isInsidePopup) {
    closeDropdown()
  }
}

// Scroll/resize close
function onScrollOrResize() {
  if (isOpen.value) closeDropdown()
}

// Escape key
function onKeydown(event) {
  if (event.key === 'Escape' && isOpen.value) {
    closeDropdown()
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('scroll', onScrollOrResize, { passive: true })
  window.addEventListener('resize', onScrollOrResize)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('scroll', onScrollOrResize)
  window.removeEventListener('resize', onScrollOrResize)
})
</script>

<style scoped>
.app-status-dropdown {
  display: inline-flex;
  align-items: center;
  position: relative;
}

.status-trigger {
  display: inline-flex;
}

.status-trigger--active {
  filter: brightness(1.1);
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.18);
  border-radius: 6px;
}

/*
 * Popup styles — matches the existing .status-popup-fixed in ApplicationsView.
 * Intentionally :global(): the popup is teleported to <body>, so scoped
 * selectors can't reach it. Do not remove the :global() wrappers.
 */
:global(.status-popup-fixed) {
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 8px;
  padding: 4px;
  min-width: 150px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}

:global(.dropdown-item) {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 12px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text, #1e293b);
  border-radius: 4px;
}

:global(.dropdown-item:hover) {
  background: #f1f5f9;
}

:global(.dropdown-item--danger) {
  color: #dc2626;
}

:global(.dropdown-item--danger:hover) {
  background: #fef2f2;
}

:global(.dropdown-divider) {
  height: 1px;
  background: var(--border, #e2e8f0);
  margin: 4px 0;
}
</style>