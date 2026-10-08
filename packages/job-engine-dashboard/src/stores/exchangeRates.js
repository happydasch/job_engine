import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * Exchange rates and profile currency store.
 *
 * Fetches live exchange rates from /api/exchange-rates (backed by
 * job_engine.currency_converter with live API + disk cache) and provides
 * conversion helpers for job salary display.
 *
 * Singleton — state is shared across all components.
 */
export const useExchangeRatesStore = defineStore('exchangeRates', () => {
  const profileCurrency = ref('USD')
  const exchangeRates = ref({})
  const loaded = ref(false)
  const loading = ref(false)
  const loadedAt = ref(0)
  const REFRESH_INTERVAL = 5 * 60 * 1000 // 5 minutes

  async function loadProfile() {
    if (loading.value) return
    // Allow re-fetch if TTL has expired
    if (loaded.value && Date.now() - loadedAt.value < REFRESH_INTERVAL) return
    loading.value = true
    try {
      // Fetch live exchange rates from the backend (currency_converter.py with API cache)
      const res = await fetch('/api/exchange-rates')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      profileCurrency.value = (data.profile_currency || 'USD').toUpperCase()
      exchangeRates.value = data.rates || {}
      loaded.value = true
      loadedAt.value = Date.now()
    } catch (e) {
      console.error('Failed to load exchange rates:', e)
      // Fallback: try loading from profile static rates
      try {
        const res2 = await fetch('/api/profile/data')
        if (res2.ok) {
          const profile = await res2.json()
          profileCurrency.value = (profile.currency || 'USD').toUpperCase()
          exchangeRates.value = profile.exchange_rates?.rates || {}
          loaded.value = true
          loadedAt.value = Date.now()
        }
      } catch (e2) {
        console.error('Fallback profile load also failed:', e2)
        // Defaults stay as USD
      }
    } finally {
      loading.value = false
    }
  }

  function getRate(fromCurrency, toCurrency) {
    if (!fromCurrency || !toCurrency) return null
    const f = fromCurrency.toUpperCase()
    const t = toCurrency.toUpperCase()
    if (f === t) return 1

    const rates = exchangeRates.value
    const fromRate = rates[f]
    const toRate = rates[t]
    // All rates are relative to USD, so: rate = toRate / fromRate
    if (fromRate == null || toRate == null) return null
    return toRate / fromRate
  }

  function convertAmount(amount, fromCurrency) {
    if (amount == null) return null
    const pc = profileCurrency.value
    if (fromCurrency?.toUpperCase() === pc) return amount
    const rate = getRate(fromCurrency, pc)
    if (rate === null) return amount
    return amount * rate
  }

  function formatNumber(v, decimals = 0) {
    if (v == null) return ''
    if (v >= 1000 && decimals === 0) {
      // Use k notation for large numbers
      return `${Math.round(v / 1000)}k`
    }
    return Number(v).toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
  }

  function formatSalaryWithConversion(amount, fromCurrency) {
    if (amount == null) return ''
    const fromUpper = (fromCurrency || 'USD').toUpperCase()
    const pc = profileCurrency.value

    if (fromUpper === pc) {
      return `${formatNumber(amount)} ${pc}`
    }

    const converted = convertAmount(amount, fromCurrency)
    if (converted === amount) {
      // Conversion failed — show original
      return `${formatNumber(amount)} ${fromUpper}`
    }

    // Show both: "12,500 PLN (≈3,125 USD)"
    return `${formatNumber(amount)} ${fromUpper} (≈${formatNumber(converted)} ${pc})`
  }

  function formatSalaryRange(min, max, currency) {
    const fromUpper = (currency || 'USD').toUpperCase()
    const pc = profileCurrency.value

    if (!min && !max) return ''

    if (min && max) {
      if (fromUpper === pc) {
        return `${formatNumber(min)} - ${formatNumber(max)} ${pc}`
      }
      // Show both: "10,000 - 15,000 PLN (≈2,500 - 3,750 USD)"
      const cMin = convertAmount(min, currency)
      const cMax = convertAmount(max, currency)
      if (cMin !== null && cMax !== null && cMin !== min) {
        return `${formatNumber(min)} - ${formatNumber(max)} ${fromUpper} (≈${formatNumber(cMin)} - ${formatNumber(cMax)} ${pc})`
      }
      return `${formatNumber(min)} - ${formatNumber(max)} ${fromUpper}`
    }
    const fmt = (v, showConverted = true) => {
      if (v == null) return ''
      const formatted = formatNumber(v)
      const converted = showConverted ? convertAmount(v, currency) : null
      if (converted !== null && converted !== v && fromUpper !== pc) {
        return `${formatted} ${fromUpper} (≈${formatNumber(converted)} ${pc})`
      }
      return `${formatted} ${fromUpper}`
    }
    if (min) return fmt(min)
    return fmt(max)
  }

  /**
   * Returns separate source and converted salary text for stacked display.
   * When no conversion is needed (same currency), converted is null.
   */
  function getSalaryParts(min, max, currency) {
    const fromUpper = (currency || 'USD').toUpperCase()
    const pc = profileCurrency.value

    if (!min && !max) return { source: '', converted: null }

    const fmtVal = (v) => formatNumber(v)
    const fmtRange = (v1, v2, cur) => {
      if (v1 != null && v2 != null) return `${fmtVal(v1)}-${fmtVal(v2)} ${cur}`
      if (v1 != null) return `From ${fmtVal(v1)} ${cur}`
      return `Up to ${fmtVal(v2)} ${cur}`
    }

    // Same currency — no conversion
    if (fromUpper === pc) {
      return { source: fmtRange(min, max, pc), converted: null }
    }

    // Different currency — try to convert
    const cMin = min != null ? convertAmount(min, currency) : null
    const cMax = max != null ? convertAmount(max, currency) : null

    if (cMin === min && cMax === max) {
      // Conversion failed or no rates available — show source only
      return { source: fmtRange(min, max, fromUpper), converted: null }
    }

    return {
      source: fmtRange(cMin, cMax, pc),
      converted: fmtRange(min, max, fromUpper),
    }
  }

  function hasConversion(min, max, currency) {
    const parts = getSalaryParts(min, max, currency)
    return parts.converted !== null
  }

  function simpleFormat(min, max, currency) {
    const fromUpper = (currency || 'USD').toUpperCase()
    const pc = profileCurrency.value

    if (!min && !max) return ''

    const fmtVal = (v) => formatNumber(v)

    if (fromUpper === pc) {
      if (min && max) return `${fmtVal(min)}-${fmtVal(max)} ${pc}`
      if (min) return `From ${fmtVal(min)} ${pc}`
      return `Up to ${fmtVal(max)} ${pc}`
    }

    // Different currency — try to convert
    const cMin = min ? convertAmount(min, currency) : null
    const cMax = max ? convertAmount(max, currency) : null

    if (min && max) {
      return `${fmtVal(min)}-${fmtVal(max)} ${fromUpper} (${fmtVal(cMin)}-${fmtVal(cMax)} ${pc})`
    }
    if (min) {
      return `From ${fmtVal(min)} ${fromUpper} (${fmtVal(cMin)} ${pc})`
    }
    return `Up to ${fmtVal(max)} ${fromUpper} (${fmtVal(cMax)} ${pc})`
  }

  /**
   * Force a re-fetch of exchange rates regardless of TTL.
   */
  async function forceLoad() {
    loadedAt.value = 0
    loaded.value = false
    await loadProfile()
  }

  return {
    profileCurrency,
    forceLoad,
    loadedAt,
    loadProfile,
    convertAmount,
    formatSalaryWithConversion,
    formatSalaryRange,
    simpleFormat,
    formatNumber,
    getRate,
    getSalaryParts,
    hasConversion,
  }
})