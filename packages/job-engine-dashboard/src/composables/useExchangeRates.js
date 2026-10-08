/**
 * Exchange rates and profile currency composable.
 *
 * Delegates to the Pinia store so Vue DevTools can inspect state.
 *
 * Usage:
 *   const { profileCurrency, convertSalary, formatSalaryRange, getSalaryParts } = useExchangeRates()
 *   await loadProfile()
 *   convertSalary(50000, 'PLN')  // → 12500
 *   formatSalaryRange(4000, 5000, 'PLN')  // → "4,000 PLN (≈1,000 USD)"
 *   getSalaryParts(4000, 5000, 'PLN')     // → {source: "4k-5k PLN", converted: "1k-1.3k USD"}
 */

import { useExchangeRatesStore } from '../stores/exchangeRates'

export function useExchangeRates() {
  const store = useExchangeRatesStore()
  return {
    profileCurrency: store.profileCurrency,
    loadProfile: store.loadProfile,
    convertAmount: store.convertAmount,
    formatSalaryWithConversion: store.formatSalaryWithConversion,
    formatSalaryRange: store.formatSalaryRange,
    simpleFormat: store.simpleFormat,
    formatNumber: store.formatNumber,
    getRate: store.getRate,
    getSalaryParts: store.getSalaryParts,
    hasConversion: store.hasConversion,
  }
}