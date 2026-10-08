import { ref, watch } from 'vue'
import { useScraperStatusStore } from '../stores/scraperStatus'

/**
 * Reactive composable that calls `callback` whenever a scrape run completes.
 *
 * Watches the shared `scraperStatusStore.lastRunCompletedAt` timestamp — the
 * store increments this on every running→completed transition, whether triggered
 * from the UI, a schedule, or a cron job.
 *
 * @param {() => void} callback - Function to call when a scrape completes.
 */
export function useRefreshOnScrapeComplete(callback) {
  const scraperStore = useScraperStatusStore()
  const lastCompleted = ref(scraperStore.lastRunCompletedAt)

  watch(
    () => scraperStore.lastRunCompletedAt,
    (newVal) => {
      if (newVal !== lastCompleted.value) {
        lastCompleted.value = newVal
        callback()
      }
    },
  )
}