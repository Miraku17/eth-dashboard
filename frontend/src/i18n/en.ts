/**
 * Source of truth for translation keys. The type
 * `keyof typeof en` is what other layers consume to ensure type-safe
 * key lookup. Task 3 fills this out with the full ~250-key inventory.
 */
export const en = {
  // Navigation (will be expanded in Task 3 alongside the full inventory)
  "nav.overview": "Overview",
  "nav.markets": "Markets",
  "nav.onchain": "Onchain",
  "nav.mempool": "Mempool",

  // Common UI
  "common.loading": "loading…",
  "common.unavailable": "unavailable",
} as const;
