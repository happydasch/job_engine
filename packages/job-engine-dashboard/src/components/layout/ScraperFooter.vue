<template>
  <footer class="scraper-footer">
    <div class="scraper-footer-left">
      <BaseButton v-if="!isRunning" variant="primary" size="sm" @click="triggerRun()"><AppIcon name="play" filled /> Run</BaseButton>
      <BaseButton v-if="isRunning" variant="danger" size="sm" @click="cancelRun()" aria-label="Stop scraping"><AppIcon name="square" filled /> Stop</BaseButton>
      <span class="scraper-dot" :class="isRunning ? 'dot-running' : 'dot-idle'"></span>
      <span class="scraper-status-text">{{ isRunning ? 'Scraping in progress...' : 'Idle' }}</span>
      <div v-if="isRunning" class="scraper-footer-progress hide-mobile">
        <div class="scraper-footer-progress-fill" :style="{ width: progress + '%' }"></div>
      </div>
    </div>
    <div class="scraper-footer-right">
      <span v-if="lastRun && !isRunning" class="last-run-text">Last run: {{ lastRun }}</span>
      <router-link to="/scrapers" class="scraper-footer-link" title="Scrapers">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-sm">
          <path d="M12 2a3 3 0 0 0-3 3v1h6V5a3 3 0 0 0-3-3z"/><path d="M5 12h14"/><path d="M5 12a3 3 0 0 1-3-3v-1h6v1a3 3 0 0 1-3 3z"/><path d="M19 12a3 3 0 0 0 3-3v-1h-6v1a3 3 0 0 0 3 3z"/><path d="M12 12v10"/><path d="M8 22h8"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/>
        </svg>
      </router-link>
    </div>
  </footer>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useScraperStatusStore } from '../../stores/scraperStatus'
import BaseButton from '../common/BaseButton.vue'
import AppIcon from '../common/AppIcon.vue'

import { useDateTime } from '../../composables/useDateTime'

const store = useScraperStatusStore()
const { progress, isRunning, history } = storeToRefs(store)
const { triggerRun, cancelRun } = store
const { timeAgo } = useDateTime()

const lastRun = computed(() => {
  const started = history.value[0]?.started_at
  return started ? timeAgo(started) : ''
})

onMounted(() => {
  // init() is idempotent — App.vue owns the loop; this just covers the
  // (unlikely) case the footer mounts before App's onMounted fires
  store.init()
})
</script>

<style scoped>
.scraper-footer {
  padding: 10px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  font-size: 13px;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--surface);
  border-top: 1px solid var(--border);
}
.scraper-footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.scraper-footer-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.scraper-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-running { background: #22c55e; animation: pulse 1.5s infinite; }
.dot-idle { background: var(--muted); }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.scraper-status-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  flex-shrink: 0;
}
.scraper-footer-progress {
  height: 6px;
  background: var(--border);
  flex: 1;
  border-radius: 3px;
  overflow: hidden;
  min-width: 80px;
}
.scraper-footer-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #16a34a);
  border-radius: 3px;
  transition: width 0.3s ease;
}
.last-run-text {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.scraper-footer-link {
  font-size: 12px;
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
  white-space: nowrap;
}
.scraper-footer-link:hover {
  text-decoration: underline;
}
.scraper-footer-link svg {
  width: 14px;
  height: 14px;
  display: block;
}
.hide-mobile {
  display: block;
}
@media (max-width: 640px) {
  .hide-mobile {
    display: none;
  }
}
</style>