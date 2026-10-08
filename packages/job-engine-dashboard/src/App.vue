<template>
  <div id="app-shell">
    <NavBar :active-sidebar="sidebarVisible ? sidebarActivePanel : null" @toggle-scrapers="openSidebar('scrapers')" @toggle-profile="openSidebar('profile')" @toggle-settings="openSidebar('settings')" />
    <main class="main-content">
      <router-view />
    </main>
    <ScraperFooter />
    <ToastNotifications />
    <SidebarPanel
      :visible="sidebarVisible"
      :active-panel="sidebarActivePanel"
      @update:active-panel="sidebarActivePanel = $event"
      @close="sidebarVisible = false"
    />
  </div>
</template>

<script setup>
import { onErrorCaptured, onMounted, provide } from 'vue'
import { useLocalStorage } from './composables/useLocalStorage'
import { useScraperStatusStore } from './stores/scraperStatus'
import NavBar from './components/layout/NavBar.vue'
import ScraperFooter from './components/layout/ScraperFooter.vue'
import ToastNotifications from './components/common/ToastNotifications.vue'
import SidebarPanel from './components/layout/SidebarPanel.vue'

const sidebarVisible = useLocalStorage('job_engine_sidebar_visible', false)
const sidebarActivePanel = useLocalStorage('job_engine_sidebar_active_panel', 'scrapers')

// Own the scraper-status singleton's poll loop for the app lifetime —
// individual views/components must NOT call destroy() (they come and go).
onMounted(() => {
  useScraperStatusStore().init()
})

function openSidebar(panel) {
  sidebarActivePanel.value = panel
  sidebarVisible.value = true
}

provide('openSidebar', openSidebar)

// Catch render errors at the root level and prevent error propagation
// from destroying the entire component tree. Without this, a single
// component crash can bring down the router-view, making the app
// appear frozen until a full page reload.
onErrorCaptured((err, _instance, info) => {
  console.error(`[App onErrorCaptured] ${info}:`, err)
  return false // Prevent propagation — let the app recover
})
</script>

<style>
/*
 * Intentionally UNSCOPED: This block imports legacy CSS via Vite's @import
 * pipeline (./dashboard/static/css/style.css) and defines app-level layout
 * styles (#app-shell, .main-content) that are global by design. The legacy
 * CSS import must remain global, and the layout rules are the root-level
 * foundational grid — scoping them would break the full-page layout.
 */
/* Import legacy CSS through Vite's build pipeline instead of a runtime link.
   This eliminates the "doesn't exist at build time" warning from Vite. */
@import './dashboard/static/css/style.css';

#app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.main-content {
  flex: 1;
  padding: 1.5rem;
  padding-bottom: calc(1.5rem + 45px);
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

@media (max-width: 840px) {
  .main-content { padding: 1rem; padding-bottom: calc(1rem + 45px); }
}

@media (max-width: 480px) {
  .main-content { padding: 0.75rem; padding-bottom: calc(0.75rem + 45px); }
}
</style>