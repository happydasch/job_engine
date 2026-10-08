<template>
  <nav>
    <div class="nav-inner">
      <router-link to="/" class="brand">
        Job Engine
        <small>alpha</small>
      </router-link>
      <button class="hamburger" aria-label="Menu" @click="menuOpen = !menuOpen">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="3" y1="6" x2="21" y2="6"/>
          <line x1="3" y1="12" x2="21" y2="12"/>
          <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <div class="nav-links" :class="{ open: menuOpen }">
        <router-link to="/jobs" class="nav-link" :class="{ active: $route.path.startsWith('/jobs') }">
          Jobs
          <span v-if="jobsCount" class="badge">{{ jobsCount }}</span>
        </router-link>
        <router-link to="/companies" class="nav-link" :class="{ active: $route.path.startsWith('/companies') }">Companies</router-link>
        <router-link to="/skills" class="nav-link" :class="{ active: $route.path.startsWith('/skills') }">Skills</router-link>
        <router-link to="/applications" class="nav-link" :class="{ active: $route.path.startsWith('/applications') }">Applications</router-link>
      </div>

      <div class="spacer"></div>

      <div class="nav-utils">

        <button
          type="button"
          class="nav-util-link"
          :class="{ 'nav-util-active': activeSidebar === 'scrapers' || $route.path.startsWith('/scrapers') }"
          @click="$emit('toggle-scrapers')"
          title="Scrapers"
          :aria-pressed="activeSidebar === 'scrapers'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a3 3 0 0 0-3 3v1h6V5a3 3 0 0 0-3-3z"/><path d="M5 12h14"/><path d="M5 12a3 3 0 0 1-3-3v-1h6v1a3 3 0 0 1-3 3z"/><path d="M19 12a3 3 0 0 0 3-3v-1h-6v1a3 3 0 0 0 3 3z"/><path d="M12 12v10"/><path d="M8 22h8"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/>
          </svg>
          <span class="nav-util-link-label">Scrapers</span>
        </button>

        <button
          type="button"
          class="nav-util-link"
          :class="{ 'nav-util-active': activeSidebar === 'profile' }"
          @click="$emit('toggle-profile')"
          title="Profile"
          :aria-pressed="activeSidebar === 'profile'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
          </svg>
          <span class="nav-util-link-label">Profile</span>
        </button>

        <button
          type="button"
          class="nav-util-link"
          :class="{ 'nav-util-active': activeSidebar === 'settings' }"
          @click="$emit('toggle-settings')"
          title="Settings"
          :aria-pressed="activeSidebar === 'settings'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span class="nav-util-link-label">Settings</span>
        </button>

      </div>
    </div>
  </nav>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useRefreshOnScrapeComplete } from '../../composables/useRefreshOnScrapeComplete'

const props = defineProps({
  activeSidebar: { type: String, default: null },
})

const route = useRoute()
const emit = defineEmits(['toggle-scrapers', 'toggle-profile', 'toggle-settings'])
const menuOpen = ref(false)
const jobsCount = ref(0)
let refreshInterval = null

async function refreshJobsCount() {
  try {
    const res = await fetch('/api/jobs?per_page=1')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (data && data.total) jobsCount.value = data.total
  } catch (e) {
    // Badge count is non-critical; keep the last known value
    console.error('Failed to refresh jobs count:', e)
  }
}

// Refresh after every scrape run completes
useRefreshOnScrapeComplete(() => refreshJobsCount())

// Fallback interval — catches scheduled/cron runs that happen while the user
// is on another tab or the page was idle.
onMounted(() => {
  refreshJobsCount()
  refreshInterval = setInterval(() => refreshJobsCount(), 60000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})

// Close mobile menu on route change
watch(() => route.path, () => { menuOpen.value = false })
</script>

<style scoped>
/* Reset button defaults for nav-util-link buttons */
.nav-util-link {
  background: none;
  border: none;
  font: inherit;
  cursor: pointer;
}

/* Navigation bar */
nav {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--shadow);
}

.nav-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 32px;
  height: 56px;
}

.brand {
  font-weight: 700;
  font-size: 18px;
  color: var(--primary);
  text-decoration: none;
  white-space: nowrap;
}

.brand small {
  font-weight: 400;
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 4px;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-link {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: var(--radius);
  transition: all 0.15s;
}

.nav-link:hover { color: var(--text); background: var(--bg); }
.nav-link.active { color: var(--primary); background: var(--primary-08); }

.spacer { flex: 1; }

.nav-utils {
  display: flex;
  align-items: center;
  gap: 2px;
}

.nav-utils .nav-util-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius);
  transition: all 0.15s;
  color: var(--text-secondary);
  text-decoration: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.nav-utils .nav-util-link:hover {
  color: var(--text);
  background: var(--bg);
}

.nav-utils .nav-util-active {
  color: var(--primary);
  background: var(--primary-08);
}

.nav-utils .nav-util-link svg {
  width: 16px;
  height: 16px;
  display: block;
  flex-shrink: 0;
}

.nav-utils .nav-util-link-label {
  font-size: 14px;
  font-weight: 500;
}

.hamburger {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  color: var(--text-secondary);
  font-size: 22px;
  line-height: 1;
  border-radius: var(--radius);
}

.hamburger:hover {
  color: var(--text);
  background: var(--bg);
}

.nav-link {
  white-space: nowrap;
}

.badge {
  background: var(--primary);
  color: white;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  margin-left: 4px;
}

/* Responsive — hide nav-utils labels below 1200px */
@media (max-width: 1200px) {
  .nav-utils .nav-util-link {
    padding: 6px 10px;
  }

  .nav-utils .nav-util-link-label {
    display: none;
  }
}

/* Responsive — collapse left nav-links below 840px */
@media (max-width: 840px) {
  .hamburger { display: block; }

  .nav-links {
    display: none;
    position: absolute;
    top: 56px;
    left: 0;
    right: 0;
    flex-direction: column;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 8px 16px;
    box-shadow: var(--shadow-lg);
    gap: 2px;
  }

  .nav-links.open { display: flex; }

  .nav-links .nav-link {
    padding: 10px 12px;
    width: 100%;
    border-radius: var(--radius);
  }

  .nav-inner { gap: 12px; }
}
</style>