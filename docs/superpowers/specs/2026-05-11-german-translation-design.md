# German Translation (i18n) — Design

**Date:** 2026-05-11
**Status:** Draft
**Track:** Client-comfort feature — operator's German-speaking client requested a German UI option.
**Branch:** `feature/german-translation`
**Predecessors:** None — first internationalization touch in the project.

## Goal

Add a floating EN ↔ DE language toggle that flips the dashboard's UI chrome and conversational copy between English and German, with the German translations professionally curated (not auto-generated). Persistence across sessions via `localStorage`. No backend changes.

## Non-goals

- **Multi-language support beyond DE.** This is a deliberately strict EN+DE design. If a third language is requested, that's a 1-day refactor to a real i18n library — not a v1 concern.
- **Translating data values.** Asset symbols (`USDT`, `WETH`), addresses, hashes, percentages, numeric values, DEX/venue names (`bybit`, `agni`, `uniswap_v3`) all stay English regardless of locale. This is the same convention German finance UIs use; the client expects it.
- **Translating backend-supplied strings.** The API stays English; any enum-style strings (`flow_kind`, alert payloads) get translated *client-side* via the same dictionary lookup. The backend does not become locale-aware.
- **Plural rules / locale-aware date or number formatting.** Out of scope; we have a static UI shell with limited dynamic content.
- **Server-side rendering of translations.** The dashboard is SPA-only; the locale flips at runtime in the browser.
- **A real i18n library (`react-i18next`, `react-intl`).** YAGNI. The custom Context-based approach is ~50 lines of glue and trivial to delete or upgrade later.
- **Auto-translation at runtime.** Quality is unacceptable for crypto jargon. We use manual / DeepL-assisted translations only.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Scope of "translate all" | **UI chrome + dynamic copy** (~250-300 strings) | Covers panel titles, navigation, tile labels, empty-state messages, toasts, error/loading states. Excludes data values per non-goals. |
| Architecture | **Custom React Context + flat TS dictionaries** | No new npm deps; ~50 lines of glue; easy to grep, debug, and delete. |
| Type safety | **Literal-union keys** (`type TranslationKey = keyof typeof en`) | Compile-time safety against typos and missing translations. `Record<TranslationKey, string>` on `de.ts` enforces parity. |
| Persistence | **`localStorage` key `etherscope.locale`** | Same scheme used elsewhere in the app for layout customization. |
| Toggle UX | **Fixed-position EN \| DE pill, bottom-right** | Always visible, doesn't compete with panel chrome, standard pattern. |
| Translator | **DeepL** (manual) | DeepL produces noticeably better German for technical text than Google Translate. Crypto-specific jargon (per glossary) stays English. |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  <App>                                                       │
│    <LocaleProvider>                                          │
│      <BrowserRouter> … existing layout … </BrowserRouter>    │
│      <LocaleToggle />   ← fixed bottom-right                 │
│    </LocaleProvider>                                         │
│  </App>                                                      │
│                                                              │
│  src/i18n/                                                   │
│    en.ts          flat dict; source of truth for keys        │
│    de.ts          same shape, German values                  │
│    types.ts       type Locale = "en" | "de"                  │
│                   type TranslationKey = keyof typeof en      │
│    LocaleProvider.tsx     context, provider, useT, useLocale │
│  src/components/LocaleToggle.tsx                             │
│  docs/i18n-glossary.md    translator consistency reference   │
└──────────────────────────────────────────────────────────────┘
```

The `LocaleProvider` holds two pieces of state — `locale: 'en' | 'de'` and a setter — both persisted to `localStorage`. Components read via `const t = useT();` then call `t('key.path', vars?)`. Active locale also propagates to `document.documentElement.lang` for accessibility (screen readers honor the `lang` attribute).

## Components

### 1. `frontend/src/i18n/en.ts`

The source-of-truth dictionary. Flat object with `"<namespace>.<slug>"` keys. Grouped namespaces: `nav.*`, `common.*`, `panel.*`, `tile.*`, `empty.*`, `toast.*`, `error.*`, `flow.*`, `alert.*`. Critical use of `as const` so `keyof typeof en` resolves to the literal union of keys.

Excerpt:

```ts
export const en = {
  // Navigation
  "nav.overview": "Overview",
  "nav.markets": "Markets",
  "nav.onchain": "Onchain",
  "nav.mempool": "Mempool",

  // Common UI
  "common.loading": "loading…",
  "common.unavailable": "unavailable",
  "common.no_data_yet": "no data yet",

  // Liquidations panel
  "liquidations.title": "Liquidations (24h)",
  "liquidations.subtitle": "Perp futures · ETH-USD · {{venue}}",
  "liquidations.tile.long": "Long liquidated",
  "liquidations.tile.short": "Short liquidated",
  "liquidations.empty": "no liquidations in the last {{range}} — quiet market window. Listener subscribes to Bybit's allLiquidation.ETHUSDT; events stream as they happen.",
  // …
} as const;
```

`{{var}}` placeholders are resolved by `useT()` at call time.

### 2. `frontend/src/i18n/de.ts`

Same keys, German values. Typed `Record<TranslationKey, string>` so a missing key fails the build.

```ts
import type { TranslationKey } from "./types";
export const de: Record<TranslationKey, string> = {
  "nav.overview": "Übersicht",
  "nav.markets": "Märkte",
  "nav.onchain": "On-Chain",
  "nav.mempool": "Mempool",
  // …
};
```

### 3. `frontend/src/i18n/types.ts`

```ts
import { en } from "./en";
export type Locale = "en" | "de";
export type TranslationKey = keyof typeof en;
```

### 4. `frontend/src/i18n/LocaleProvider.tsx`

Provider, context, and the two hooks (`useLocale`, `useT`):

```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { en } from "./en";
import { de } from "./de";
import type { Locale, TranslationKey } from "./types";

const STORAGE_KEY = "etherscope.locale";
const DICT = { en, de } as const;

type Ctx = { locale: Locale; setLocale: (l: Locale) => void };
const LocaleCtx = createContext<Ctx | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "de" || stored === "en" ? stored : "en";
  });
  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem(STORAGE_KEY, l);
    document.documentElement.lang = l;
  }, []);
  return <LocaleCtx.Provider value={{ locale, setLocale }}>{children}</LocaleCtx.Provider>;
}

export function useLocale() {
  const v = useContext(LocaleCtx);
  if (!v) throw new Error("useLocale outside LocaleProvider");
  return v;
}

export function useT() {
  const { locale } = useLocale();
  return useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      let s: string = DICT[locale][key] ?? en[key] ?? key;
      if (vars) for (const [k, v] of Object.entries(vars)) {
        s = s.replaceAll(`{{${k}}}`, String(v));
      }
      return s;
    },
    [locale],
  );
}
```

The fallback chain `DICT[locale][key] ?? en[key] ?? key` is defensive — the type system should make it impossible to hit, but if a runtime bug slips through (dynamic key construction, etc.), we silently degrade to English instead of crashing.

### 5. `frontend/src/components/LocaleToggle.tsx`

Floating EN | DE pill, fixed bottom-right.

```tsx
import { useLocale } from "../i18n/LocaleProvider";

export default function LocaleToggle() {
  const { locale, setLocale } = useLocale();
  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex items-center rounded-full
                 border border-slate-700 bg-slate-900/90 backdrop-blur
                 text-xs font-medium shadow-lg"
      role="group"
      aria-label="Language"
    >
      <button
        type="button"
        onClick={() => setLocale("en")}
        className={`px-3 py-1.5 rounded-full transition ${
          locale === "en" ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"
        }`}
        aria-pressed={locale === "en"}
      >EN</button>
      <button
        type="button"
        onClick={() => setLocale("de")}
        className={`px-3 py-1.5 rounded-full transition ${
          locale === "de" ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"
        }`}
        aria-pressed={locale === "de"}
      >DE</button>
    </div>
  );
}
```

`fixed bottom-4 right-4 z-50` keeps it above panel content. `aria-pressed` and `role="group"` give keyboard / screen-reader users a usable toggle.

### 6. `docs/i18n-glossary.md`

Translator-consistency reference, committed as part of Phase 1.

**Stays in English regardless of locale:**
- Asset symbols (`USDT`, `USDC`, `WETH`, `MNT`, `ETH`, `BTC`, etc.)
- DEX names (`Uniswap V2`, `Uniswap V3`, `Curve`, `Balancer`, `Agni`, `FusionX`)
- CEX names (`Binance`, `Bybit`, `OKX`, `Deribit`, `Coinbase`, `Kraken`)
- Crypto jargon: `Smart money`, `OI` (open interest), `TVL`, `LST`, `LRT`, `liquidation`, `slippage`, `MEV`
- Address strings, tx hashes
- Numeric values + percentages

**Standard German for terms we translate:**

| English | German |
|---|---|
| Whale | Wal |
| Alert | Alarm |
| Overview | Übersicht |
| Markets | Märkte |
| Onchain | On-Chain (hyphenated) |
| Network activity | Netzwerk-Aktivität |
| Settings | Einstellungen |
| Loading | Laden |
| Unavailable | Nicht verfügbar |
| Buy / Sell / Net | Kauf / Verkauf / Netto |
| Long / Short | Long / Short (English in German finance) |
| Quiet market window | ruhige Marktphase |

This glossary is consulted whenever the translator is uncertain. It prevents three different German words for "whale" depending on which translation pass produced them.

## Data flow

**Component render:**
```
<Component>
  → const t = useT()
  → t("liquidations.title")
  → useT reads `locale` from context
  → returns DICT[locale]["liquidations.title"]
  → React renders the string
```

**User clicks DE:**
```
LocaleToggle button onClick
  → setLocale("de")
  → state update + localStorage write + <html lang="de">
  → Context value changes
  → all consumers of useT re-render with new strings
```

**Page reload:**
```
LocaleProvider mounts
  → reads localStorage["etherscope.locale"]
  → initializes state to that value (default "en")
```

## Schema

None — no DB changes.

## Error handling

| Scenario | Behavior |
|---|---|
| `localStorage` unavailable (private browsing in some browsers) | `setLocale` swallows the storage error; locale still flips for the session. |
| Stored locale is not `"en"` or `"de"` (corrupted, hand-edited) | Falls back to `"en"` on mount. |
| Translation key missing at runtime (shouldn't happen due to types) | Falls back through `DICT[locale][key] → en[key] → key`. Renders the raw key as a last resort, which is visible enough to flag in QA. |
| Variable not provided to a key with `{{var}}` placeholder | Placeholder remains in the rendered string (`"{{venue}}"`). Visible during dev/QA. |

## Testing

Three small test files; everything testable in isolation. Vitest is already wired in.

### `frontend/src/i18n/__tests__/dict_completeness.test.ts`

```ts
import { en } from "../en";
import { de } from "../de";

test("DE dictionary has every EN key with a non-empty value", () => {
  for (const key of Object.keys(en) as Array<keyof typeof en>) {
    expect(de[key], `missing or empty translation for ${key}`).toBeTruthy();
  }
});

test("DE has no extra keys not in EN", () => {
  for (const key of Object.keys(de)) {
    expect(en).toHaveProperty(key);
  }
});
```

The first test catches empty values (the `Record<TranslationKey, string>` type allows `""`). The second catches keys deleted from EN but lingering in DE (slow-rotting strings).

### `frontend/src/i18n/__tests__/useT.test.tsx`

Tests covering:
- Returns EN string for a known key in EN locale.
- Returns DE string for a known key in DE locale.
- Falls back to EN if a key is missing in DE (defensive).
- Falls back to the key string if a key is missing in BOTH dicts (off-spec but safe).
- Interpolates `{{var}}` placeholders.
- `setLocale` updates `localStorage` and re-renders consumers.
- On mount, reads from `localStorage` if a saved value exists.
- Throws if `useT()` is called outside a `LocaleProvider`.

### `frontend/src/components/__tests__/LocaleToggle.test.tsx`

- Renders `EN | DE` text.
- Active half has the highlighted className.
- Clicking `DE` calls `setLocale("de")`.
- `aria-pressed` flips correctly when locale changes.

### Out of scope for automated tests

- Visual QA of every translated string — manual pass during Phase 2.
- Translation accuracy — humans + DeepL handle quality.
- The fact that backend error messages may leak through untranslated — accepted explicitly; API stays English.

## Implementation strategy: three sequential PRs

Each phase is one logical commit with a distinct failure mode. If Phase 2's translations have issues, we can ship Phases 1 and 3 and iterate on the dictionary alone.

### Phase 1 — Inventory + EN dict + extract literals

1. Walk the frontend folder, grep for hard-coded user-visible strings, categorize by panel/feature.
2. Build out `en.ts` with all keys grouped by namespace.
3. Replace each hard-coded string in components with `t('key.path')` calls. Touch every file once.
4. Add `LocaleProvider` + `useT` + `types.ts` (provider not yet mounted; just exports usable in components).
5. Build passes; UI looks identical (still English everywhere because there's no provider mounted yet, and no DE dict).

The `dict_completeness.test.ts` ships in Phase 3, not here, because it requires `de.ts` to exist.

**Verification:** `npm run build` succeeds. `grep -r "<a string we expect to translate>"` returns 0 hits in `frontend/src/components/`.

### Phase 2 — DE dict + glossary + DeepL translation

1. Run all EN values through DeepL with a prompt clarifying domain context ("German UI for a crypto trading dashboard; leave English jargon untranslated where common in German finance UIs").
2. Manually QA each value against the glossary.
3. Author `docs/i18n-glossary.md`.
4. Add `de.ts` typed as `Record<TranslationKey, string>` so any missing key fails to compile.
5. The dict-completeness test now passes.

**Verification:** `npm test` green. Manual: `localStorage.setItem('etherscope.locale','de')` in browser console, hard-refresh — visually pass through every panel, alert, and modal.

### Phase 3 — Wire LocaleProvider + LocaleToggle

1. Mount `<LocaleProvider>` at the app root, wrapping the existing layout.
2. Render `<LocaleToggle />` as a fixed sibling.
3. Add `dict_completeness.test.ts`, `useT.test.tsx`, and `LocaleToggle.test.tsx`.
4. Smoke-test: click DE, verify strings change; reload, verify DE persists; click EN, verify reverts.

**Verification:** All three test files pass. Manual click-through of the toggle confirms behavior.

## Operator setup

None. Ships as part of the frontend bundle on the next deploy. No env vars, no migrations.

## CLAUDE.md update (post-merge)

Add to `## UI polish`:

```
- German locale ✅ Floating EN/DE toggle (bottom-right pill) flips dashboard chrome + conversational copy between English and German via a custom React Context (no i18n library; flat TS dicts; type-safe via `keyof typeof en`). Persisted to `localStorage`. Excludes data values, asset symbols, DEX/CEX names, and crypto jargon (per `docs/i18n-glossary.md`). v1 is EN+DE only; adding more languages is a 1-day refactor to a real library. Spec: `docs/superpowers/specs/2026-05-11-german-translation-design.md`.
```

## Open follow-ups (not in v1)

- More languages (Spanish, Japanese, French) → migrate to `react-i18next` if and when a third language is requested.
- Backend localization (translated alert payloads, error messages) → not warranted unless a customer can't read English in their notifications.
- A small Crowdin / Lokalise pipeline for translation management → only if the dictionary grows past ~500 keys.
