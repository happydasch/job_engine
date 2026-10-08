<template>
  <transition name="sidebar">
    <div v-if="visible" class="sidebar-overlay" @click.self="$emit('close')">
      <div class="sidebar-backdrop" @click="$emit('close')"></div>
      <div class="sidebar-container">
        <div class="sidebar-header">
          <div class="sidebar-tabs">

            <button
              class="sidebar-tab"
              :class="{ active: activePanel === 'scrapers' }"
              @click="$emit('update:activePanel', 'scrapers')"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v1h6V5a3 3 0 0 0-3-3z"/>
                <path d="M5 12h14"/>
                <path d="M5 12a3 3 0 0 1-3-3v-1h6v1a3 3 0 0 1-3 3z"/>
                <path d="M19 12a3 3 0 0 0 3-3v-1h-6v1a3 3 0 0 0 3 3z"/>
                <path d="M12 12v10"/>
                <path d="M8 22h8"/>
                <path d="M9 7V5a3 3 0 0 1 6 0v2"/>
              </svg>
              Scrapers
            </button>

            <button
              class="sidebar-tab"
              :class="{ active: activePanel === 'profile' }"
              @click="$emit('update:activePanel', 'profile')"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              Profile
            </button>

            <button
              class="sidebar-tab"
              :class="{ active: activePanel === 'settings' }"
              @click="$emit('update:activePanel', 'settings')"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              Settings
            </button>

          </div>

          <button class="sidebar-close" @click="$emit('close')" title="Close sidebar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>

        </div>
        <div class="sidebar-body">
          <ScraperPanel v-if="activePanel === 'scrapers'" @close="$emit('close')" />
          <ProfilePanel v-else-if="activePanel === 'profile'" @close="$emit('close')" />
          <SettingsPanel v-else-if="activePanel === 'settings'" />
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import ScraperPanel from './ScraperPanel.vue'
import ProfilePanel from './ProfilePanel.vue'
import SettingsPanel from './SettingsPanel.vue'

defineProps({
  visible: { type: Boolean, default: false },
  activePanel: { type: String, default: 'scrapers' },
})

defineEmits(['close', 'update:activePanel'])
</script>

<style scoped>
/* Overlay */
.sidebar-overlay {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  justify-content: flex-end;
  align-items: stretch;
}
.sidebar-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
}

/* Container */
.sidebar-container {
  position: relative;
  background: var(--color-bg-card, var(--surface, #fff));
  width: 640px;
  max-width: 100vw;
  height: 100vh;
  overflow-y: auto;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
}

/* Header */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  flex-shrink: 0;
  gap: 0.5rem;
  background: var(--color-bg-card, var(--surface, #fff));
  position: sticky;
  top: 0;
  z-index: 1;
}
.sidebar-tabs {
  display: flex;
  gap: 0;
}
.sidebar-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border: none;
  background: none;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary, #64748b);
  transition: color 0.15s, border-color 0.15s;
}
.sidebar-tab:hover {
  color: var(--color-text, #1e293b);
}
.sidebar-tab.active {
  border-bottom-color: var(--color-primary, #2563eb);
  color: var(--color-primary, #2563eb);
}
.sidebar-close {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-secondary, #64748b);
  padding: 0.25rem;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
  flex-shrink: 0;
}
.sidebar-close:hover {
  color: var(--color-text, #1e293b);
  background: var(--color-bg-hover, #f1f5f9);
}

/* Body */
.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.25rem;
}

/* Transitions */
.sidebar-enter-active,
.sidebar-leave-active {
  transition: opacity 0.2s ease;
}
.sidebar-enter-active .sidebar-container,
.sidebar-leave-active .sidebar-container {
  transition: transform 0.25s ease;
}
.sidebar-enter-from,
.sidebar-leave-to {
  opacity: 0;
}
.sidebar-enter-from .sidebar-container,
.sidebar-leave-to .sidebar-container {
  transform: translateX(40px);
}
</style>