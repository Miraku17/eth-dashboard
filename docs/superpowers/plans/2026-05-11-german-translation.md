# German Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a floating EN/DE language toggle that flips the dashboard's UI chrome and conversational copy between English and German, persisted to `localStorage`.

**Architecture:** Custom React Context with two flat TypeScript dictionaries (`en.ts`, `de.ts`). Type-safe via `keyof typeof en`. Fixed-position `EN | DE` pill bottom-right. No new npm dependencies. Mounted above `AuthGate` so the toggle is reachable on the login screen too.

**Tech Stack:** React 18, TypeScript 5, Tailwind. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-11-german-translation-design.md`

**Branch:** `feature/german-translation` (already created and checked out)

---

## File map

**Create:**
- `frontend/src/i18n/types.ts` (Task 1)
- `frontend/src/i18n/en.ts` (Task 1 seeds, Task 3 fills out)
- `frontend/src/i18n/LocaleProvider.tsx` (Task 1)
- `docs/i18n-glossary.md` (Task 2)
- `frontend/src/i18n/de.ts` (Task 4)
- `frontend/src/components/LocaleToggle.tsx` (Task 5)

**Modify:**
- Every file under `frontend/src/components/` and `frontend/src/routes/` containing user-visible string literals (Task 3)
- `frontend/src/App.tsx` (Task 5 — mount provider, render toggle)
- `CLAUDE.md` (Task 5 — UI polish status entry)

**Deliberately NOT touched:**
- `frontend/package.json` — no new deps, no test infrastructure for v1
- Backend — API stays English; locale flip is client-side only
- Asset symbols, address strings, hash values, DEX/CEX names, and crypto jargon per `docs/i18n-glossary.md`

---

## Build / verification commands

The frontend has no test runner configured (verified — `package.json` has only `dev`, `build`, `preview`, `lint`). Verification per task uses:

```bash
cd frontend && npm run build      # TypeScript + Vite build; catches type and import errors
cd frontend && npm run lint       # ESLint
```

Manual smoke test for Task 5: `cd frontend && npm run dev` and click the toggle.

---

## Task 1: i18n module scaffolding (additive, not yet wired)

**Files:**
- Create: `frontend/src/i18n/types.ts`
- Create: `frontend/src/i18n/en.ts` (seeded with a small starter set; Task 3 fills it out)
- Create: `frontend/src/i18n/LocaleProvider.tsx`

This task adds the i18n machinery without changing any user-visible behavior. `LocaleProvider` is exported but not yet mounted; `en.ts` only contains a seed of 4-5 keys to validate the wiring. Components don't yet consume `useT()`.

- [ ] **Step 1: Create the seed `en.ts`**

Create `frontend/src/i18n/en.ts`:

```ts
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
```

The `as const` is critical — it gives literal types to each value so `keyof typeof en` is a precise union of key strings, not a generic `string`.

- [ ] **Step 2: Create the type module**

Create `frontend/src/i18n/types.ts`:

```ts
import type { en } from "./en";

export type Locale = "en" | "de";
export type TranslationKey = keyof typeof en;
```

- [ ] **Step 3: Create the provider, hooks, and `useT`**

Create `frontend/src/i18n/LocaleProvider.tsx`:

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

import { en } from "./en";
import type { Locale, TranslationKey } from "./types";

const STORAGE_KEY = "etherscope.locale";

type Ctx = {
  locale: Locale;
  setLocale: (l: Locale) => void;
};

const LocaleCtx = createContext<Ctx | null>(null);

function readStoredLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "de" || stored === "en" ? stored : "en";
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // Some private-browsing modes throw on setItem; tolerate the loss.
    }
    if (typeof document !== "undefined") {
      document.documentElement.lang = l;
    }
  }, []);

  return <LocaleCtx.Provider value={{ locale, setLocale }}>{children}</LocaleCtx.Provider>;
}

export function useLocale(): Ctx {
  const v = useContext(LocaleCtx);
  if (!v) throw new Error("useLocale must be used inside <LocaleProvider>");
  return v;
}

/**
 * Returns a translator function `(key, vars?) => string`.
 *
 * Lookup order: DICT[locale][key] → en[key] → key.
 * The fallback chain is defensive — the type system should prevent the
 * second and third fallbacks from ever firing in practice.
 */
export function useT() {
  const { locale } = useLocale();
  return useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>): string => {
      // Task 4 creates `de.ts` and replaces the placeholder alias below
      // with a real import. Aliasing `de` to `en` here keeps the build
      // green for Task 1 (where useT is exported but not yet consumed
      // by any component, and de.ts doesn't exist yet).
      const dicts: Record<Locale, Record<string, string>> = {
        en,
        de: en,
      };
      let s: string = dicts[locale][key] ?? en[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          s = s.replaceAll(`{{${k}}}`, String(v));
        }
      }
      return s;
    },
    [locale],
  );
}
```

The temporary `de: en` aliasing avoids a build break if Task 4 hasn't landed yet. Task 4 replaces it with the real `import { de } from "./de";`.

- [ ] **Step 4: Verify the build**

```bash
cd frontend && npm run build
```

Expected: build succeeds. The new `i18n/` files are unused so they emit nothing user-visible, but TypeScript compiles them and confirms there are no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/i18n/types.ts frontend/src/i18n/en.ts frontend/src/i18n/LocaleProvider.tsx
git commit -m "feat(i18n): scaffolding — locale provider, useT hook, seed dictionary"
```

---

## Task 2: Translator-consistency glossary

**Files:**
- Create: `docs/i18n-glossary.md`

Standalone documentation task. Locks down the rules a translator needs to follow before authoring `de.ts` in Task 4 (avoids three different German words for "whale" depending on which translation pass produced them).

- [ ] **Step 1: Create the glossary**

Create `docs/i18n-glossary.md`:

```markdown
# i18n Glossary

Reference for translators authoring `frontend/src/i18n/de.ts` (and any
future locale files). Updated as new domain terms appear.

## Stays in English regardless of locale

These are crypto/finance jargon that German finance audiences read in
English. Translating them produces awkward output (e.g. "Smart-Geld").

- **Asset symbols:** USDT, USDC, USDS, DAI, PYUSD, FDUSD, GHO, EUROC,
  ZCHF, EURCV, EURe, tGBP, USDe, XSGD, BRZ, EURS, WETH, ETH, BTC, MNT,
  mETH, stETH, rETH, cbETH, sfrxETH, swETH, ETHx
- **DEX names:** Uniswap V2, Uniswap V3, Curve, Balancer, Sushi,
  Pancake, Maverick, Agni, FusionX, Cleopatra, Butter, Merchant Moe
- **CEX names:** Binance, Bybit, OKX, Deribit, Coinbase, Kraken
- **Concept terms:** Smart money, OI (Open Interest), TVL, LST, LRT,
  liquidation, slippage, MEV, mempool, perp, perpetual, futures,
  forceOrder, allLiquidation, long, short, basis
- **Identifiers:** addresses (0x…), tx hashes, block numbers
- **Numeric values + units:** percentages, USD, ETH, gwei, gas

## Standard German translations

For terms we DO translate, use these consistently:

| English | German |
|---|---|
| Whale | Wal |
| Whale transfer | Wal-Transfer |
| Alert | Alarm |
| Alert rule | Alarm-Regel |
| Overview | Übersicht |
| Markets | Märkte |
| Onchain | On-Chain (hyphenated) |
| Mempool | Mempool (kept as proper noun) |
| Network activity | Netzwerk-Aktivität |
| Settings | Einstellungen |
| Save / Cancel | Speichern / Abbrechen |
| Loading | Laden |
| Unavailable | Nicht verfügbar |
| Buy / Sell / Net | Kauf / Verkauf / Netto |
| Quiet market window | ruhige Marktphase |
| Transfer | Transfer (kept) |
| Pending | Ausstehend |
| Price | Preis |
| Volume | Volumen |
| Holdings | Bestände |
| Linked wallets | Verknüpfte Wallets |
| Cluster / Counterparty | Cluster / Gegenpartei |
| Smart only (toggle) | Nur Smart Money |
| no data yet | noch keine Daten |
| no liquidations in the last 24h | keine Liquidationen in den letzten 24 Std. |
| 24h | 24 Std. |
| Last update / event | Letzte Aktualisierung / Ereignis |

## Tone guidelines

- Use formal German ("Sie", not "Du"). The audience is institutional /
  professional traders.
- Prefer compact compound nouns where natural ("Netzwerk-Aktivität",
  not "Aktivität des Netzwerks").
- Use the German period (".") as the thousands separator only in prose;
  the numeric formatting in the dashboard stays English-locale (commas).

## How translators use this file

When unsure about a term, check the table above first. If a new term
isn't listed, add it here in the same PR as the translation, so the
next translator (or a future audit) sees the decision.
```

- [ ] **Step 2: Commit**

```bash
git add docs/i18n-glossary.md
git commit -m "docs(i18n): translator-consistency glossary"
```

---

## Task 3: String inventory + extraction (THE BIG TASK)

**Files:**
- Modify: `frontend/src/i18n/en.ts` (replace seed with full ~250-key dictionary)
- Modify: every component file under `frontend/src/components/` and `frontend/src/routes/` that contains user-visible string literals

This is the largest task in the plan: walk every page/panel/component, identify hard-coded user-visible strings, add keys to `en.ts`, and replace each literal with a `useT()` call. The UI looks identical after this task because the locale provider isn't mounted yet — every `useT` call returns the English value.

### Inventory rules

**DO extract:**
- Panel titles + subtitles (`title="Whale transfers"`)
- Tile labels (`<Tile label="Long liquidated" …>`)
- Empty-state copy (`"no data yet — set MANTLE_WS_URL…"`)
- Loading / error states (`"loading…"`, `"unavailable"`)
- Section headings (`"Stablecoins"`, `"Staking"`, etc. on the Onchain page)
- Navigation labels (`"Overview"`, `"Markets"`)
- Button text (`"Save"`, `"Cancel"`, `"Add rule"`)
- Form field labels and placeholders
- Toast / notification messages
- Table column headers
- Tooltip text
- Subtitle text in `<Card subtitle="…">`
- Modal / drawer headings
- Confirmation prompts

**DO NOT extract:**
- Asset symbols (`"USDT"`, `"WETH"`, `"MNT"`, `"ETH"`)
- Address strings, tx hashes, block numbers
- Numeric values, percentage signs, unit suffixes (`"%"`, `"USD"`, `"M"`, `"k"`)
- DEX / CEX names (`"agni"`, `"bybit"`, `"uniswap_v3"`)
- Crypto jargon per `docs/i18n-glossary.md` (`"Smart money"`, `"OI"`, `"TVL"`, `"liquidation"`, `"long"`, `"short"`, …)
- Format strings that combine the above (`` `Perp futures · ETH-USD · ${venue}` `` — but the literal "Perp futures · ETH-USD ·" portion IS extractable; use a `{{venue}}` placeholder)
- API enum strings rendered raw (the *display label* for an enum gets a translation key; the enum value itself stays English)

### Key naming convention

`<scope>.<slot>[.<sub>]`. Scope examples:
- `nav.*` — top navigation
- `common.*` — re-used across components (`common.loading`, `common.unavailable`, `common.no_data_yet`, `common.save`, `common.cancel`)
- `<panel-id>.title`, `<panel-id>.subtitle`, `<panel-id>.empty`, `<panel-id>.tile.<name>` — per-panel strings, where `<panel-id>` is kebab-case from `panelRegistry.ts` (`liquidations`, `mantle-order-flow`, etc.)
- `flow.<enum_value>` — labels for flow_kind enums (`flow.to_exchange` → "To CEX")
- `alert.*` — alert form, alert events, toast copy
- `wallet.*` — wallet drawer surfaces

### Concrete before/after

**`frontend/src/components/LiquidationsPanel.tsx`:**

Before (excerpt):

```tsx
<Card title="Liquidations (24h)"
      subtitle={`Perp futures · ETH-USD · ${summary?.venue ?? "bybit"}`}>
  …
  {empty && (
    <p className="p-5 text-sm text-slate-500">
      no liquidations in the last {range} — quiet market window. Listener
      subscribes to Bybit's allLiquidation.ETHUSDT; events stream as they happen.
    </p>
  )}
  …
  <Tile label="Long liquidated" value={…} tone="up" />
  <Tile label="Short liquidated" value={…} tone="down" />
```

After:

```tsx
import { useT } from "../i18n/LocaleProvider";

export default function LiquidationsPanel() {
  const t = useT();
  // … existing hooks …

  return (
    <Card title={t("liquidations.title")}
          subtitle={t("liquidations.subtitle", { venue: summary?.venue ?? "bybit" })}>
      …
      {empty && (
        <p className="p-5 text-sm text-slate-500">
          {t("liquidations.empty", { range })}
        </p>
      )}
      …
      <Tile label={t("liquidations.tile.long")} value={…} tone="up" />
      <Tile label={t("liquidations.tile.short")} value={…} tone="down" />
    );
}
```

Corresponding additions to `en.ts`:

```ts
"liquidations.title": "Liquidations (24h)",
"liquidations.subtitle": "Perp futures · ETH-USD · {{venue}}",
"liquidations.empty": "no liquidations in the last {{range}} — quiet market window. Listener subscribes to Bybit's allLiquidation.ETHUSDT; events stream as they happen.",
"liquidations.tile.long": "Long liquidated",
"liquidations.tile.short": "Short liquidated",
```

### Workflow

- [ ] **Step 1: Inventory pass**

Walk every file under `frontend/src/components/` and `frontend/src/routes/`, identify user-visible string literals per the inventory rules. Build the full list of keys in your head or in a scratchpad.

- [ ] **Step 2: Populate `en.ts`**

Replace the seed `frontend/src/i18n/en.ts` from Task 1 with the full dictionary. Keys grouped by namespace, alphabetically within group. Use `{{var}}` placeholders for any interpolated values. The file will end up around 200-300 entries.

- [ ] **Step 3: Replace literals across all components**

Go file by file. In each one:

1. Add `import { useT } from "../i18n/LocaleProvider";` (adjust relative path).
2. Inside the component body, add `const t = useT();` near the top.
3. Replace each user-visible string literal with a `t("scope.slot")` call.
4. For interpolated strings (template literals or string concatenation involving variables), pass the variables as the second argument: `t("scope.slot", { venue, range })` — and use `{{venue}}` `{{range}}` placeholders in the dictionary value.

Common files to touch (non-exhaustive — your inventory pass surfaces the full list):

- `routes/OverviewPage.tsx`, `MarketsPage.tsx`, `OnchainPage.tsx`, `MempoolPage.tsx`
- `components/DashboardShell.tsx` (top nav)
- All `*Panel.tsx` files (27 of them per `ls components/`)
- `components/AlertEventsPanel.tsx`, `components/alerts/RuleForm.tsx`
- `components/WalletDrawer.tsx`
- `components/PriceChart.tsx`, `PriceHero.tsx`
- Any toasts, modals, confirmation dialogs

- [ ] **Step 4: Verify the build**

```bash
cd frontend && npm run build
```

Expected: succeeds. TypeScript validates that every `t("…")` call uses a key that exists in `en.ts`. Any typo or missing key is a compile error.

- [ ] **Step 5: Verify the lint**

```bash
cd frontend && npm run lint
```

Expected: no errors. (Warnings about `useCallback`/`useMemo` are tolerable.)

- [ ] **Step 6: Spot-check the running app still looks like English**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`, click around. Every panel should render exactly as before. If something says `"liquidations.title"` instead of `"Liquidations (24h)"`, the t() call references a non-existent key — the type system should have caught that, so it points to a key collision or a stale build.

Stop the dev server (Ctrl+C) when done.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/en.ts frontend/src/components/ frontend/src/routes/
git commit -m "feat(i18n): extract user-visible strings into en.ts dictionary"
```

---

## Task 4: German translations (de.ts)

**Files:**
- Create: `frontend/src/i18n/de.ts`
- Modify: `frontend/src/i18n/LocaleProvider.tsx` — replace `de: en` placeholder with real `import`

This task produces the German translations and wires them into the provider. After this task, flipping `localStorage["etherscope.locale"] = "de"` and reloading shows the dashboard in German.

- [ ] **Step 1: Author `de.ts`**

Create `frontend/src/i18n/de.ts`. The skeleton:

```ts
/**
 * German translations. Type-checked against `en.ts` via
 * `Record<TranslationKey, string>` — TypeScript fails the build if any
 * key is missing or has a non-string value.
 *
 * Translation rules: see `docs/i18n-glossary.md`. Crypto jargon, asset
 * symbols, and DEX/CEX names stay English. Use formal German ("Sie")
 * for all user-facing prompts.
 */
import type { TranslationKey } from "./types";

export const de: Record<TranslationKey, string> = {
  "nav.overview": "Übersicht",
  "nav.markets": "Märkte",
  "nav.onchain": "On-Chain",
  "nav.mempool": "Mempool",

  "common.loading": "Laden…",
  "common.unavailable": "Nicht verfügbar",
  "common.no_data_yet": "Noch keine Daten",

  "liquidations.title": "Liquidationen (24 Std.)",
  "liquidations.subtitle": "Perp Futures · ETH-USD · {{venue}}",
  "liquidations.empty": "Keine Liquidationen in den letzten {{range}} — ruhige Marktphase. Listener abonniert Bybit's allLiquidation.ETHUSDT; Ereignisse streamen in Echtzeit.",
  "liquidations.tile.long": "Long liquidiert",
  "liquidations.tile.short": "Short liquidiert",

  // … fill out every key from en.ts using docs/i18n-glossary.md as reference …
};
```

Translation approach:

1. Use DeepL (deepl.com — free tier handles small batches) for first-pass translations. Paste each EN value, get the DE value. DeepL produces noticeably better German for technical text than Google Translate.
2. For each translated value, cross-reference `docs/i18n-glossary.md`. If a term is in the "stays English" list, leave it English in the DE value too. If it's in the "standard German translations" table, use the listed term consistently.
3. Preserve `{{var}}` placeholders verbatim — do not translate the variable names.
4. Use formal "Sie" register, not "Du".
5. Keep punctuation natural for German (e.g. `24 Std.` not `24h`, German uses spaces around units).

For ~250 strings this is a focused 30-60 minutes of translator work. The `Record<TranslationKey, string>` type ensures every key from `en.ts` has a DE value before the build passes.

- [ ] **Step 2: Wire `de.ts` into the provider**

Open `frontend/src/i18n/LocaleProvider.tsx` and replace the placeholder `de: en` mapping (introduced in Task 1 to keep the build green) with a real import. Find this block in `useT`:

```tsx
// Task 4 creates `de.ts` and replaces the placeholder alias below
// with a real import. Aliasing `de` to `en` here keeps the build
// green for Task 1 (where useT is exported but not yet consumed
// by any component, and de.ts doesn't exist yet).
const dicts: Record<Locale, Record<string, string>> = {
  en,
  de: en,
};
```

Replace with:

```tsx
const dicts: Record<Locale, Record<string, string>> = {
  en,
  de,
};
```

And add the import at the top of the file:

```tsx
import { de } from "./de";
```

- [ ] **Step 3: Verify the build**

```bash
cd frontend && npm run build
```

Expected: succeeds. TypeScript verifies that `de.ts` has every key from `en.ts` (via the `Record<TranslationKey, string>` annotation). If any key is missing, you'll see an error like `Property "liquidations.empty" is missing in type ...`.

If you see compile errors about missing keys, you missed one in Step 1 — add it and re-build.

- [ ] **Step 4: Manually flip locale and visually QA**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173. In the browser console:

```js
localStorage.setItem("etherscope.locale", "de");
location.reload();
```

The toggle isn't built yet (Task 5), but `useT` reads `locale` from the provider's initial state, which reads `localStorage`. So a manual flip + reload renders the dashboard in German.

Walk through every page (Overview, Markets, Onchain, Mempool). Open the wallet drawer (click any address). Open the alert form. Confirm:

- Every translated surface reads as natural German.
- Asset symbols, addresses, numbers stay unchanged.
- Variable interpolation works (e.g. `liquidations.subtitle` shows the actual venue, not the literal `{{venue}}`).
- No layout breakage from longer German strings (German is typically 20-30% longer; check tile labels especially).

Flip back via:

```js
localStorage.setItem("etherscope.locale", "en");
location.reload();
```

Stop the dev server.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/i18n/de.ts frontend/src/i18n/LocaleProvider.tsx
git commit -m "feat(i18n): German translations + wire de.ts into provider"
```

---

## Task 5: LocaleToggle + mount provider + CLAUDE.md

**Files:**
- Create: `frontend/src/components/LocaleToggle.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `CLAUDE.md`

Final task. Adds the floating toggle, mounts the provider above `AuthGate` so the toggle is reachable everywhere (including on the login screen), and updates the project status doc.

- [ ] **Step 1: Create the toggle component**

Create `frontend/src/components/LocaleToggle.tsx`:

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
          locale === "en"
            ? "bg-slate-700 text-white"
            : "text-slate-400 hover:text-slate-200"
        }`}
        aria-pressed={locale === "en"}
      >
        EN
      </button>
      <button
        type="button"
        onClick={() => setLocale("de")}
        className={`px-3 py-1.5 rounded-full transition ${
          locale === "de"
            ? "bg-slate-700 text-white"
            : "text-slate-400 hover:text-slate-200"
        }`}
        aria-pressed={locale === "de"}
      >
        DE
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Mount provider + render toggle in `App.tsx`**

Open `frontend/src/App.tsx`. The current shape:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import AuthGate from "./components/AuthGate";
import DashboardShell from "./components/DashboardShell";
import WalletDrawer from "./components/WalletDrawer";
import MarketsPage from "./routes/MarketsPage";
import MempoolPage from "./routes/MempoolPage";
import OnchainPage from "./routes/OnchainPage";
import OverviewPage from "./routes/OverviewPage";

export default function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <Routes>
          <Route element={<DashboardShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="markets" element={<MarketsPage />} />
            <Route path="onchain" element={<OnchainPage />} />
            <Route path="mempool" element={<MempoolPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <WalletDrawer />
    </AuthGate>
  );
}
```

Wrap the entire return value in `<LocaleProvider>` (above `AuthGate` so the toggle is visible on the login screen too) and render `<LocaleToggle />` as a sibling:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import AuthGate from "./components/AuthGate";
import DashboardShell from "./components/DashboardShell";
import LocaleToggle from "./components/LocaleToggle";
import WalletDrawer from "./components/WalletDrawer";
import { LocaleProvider } from "./i18n/LocaleProvider";
import MarketsPage from "./routes/MarketsPage";
import MempoolPage from "./routes/MempoolPage";
import OnchainPage from "./routes/OnchainPage";
import OverviewPage from "./routes/OverviewPage";

export default function App() {
  return (
    <LocaleProvider>
      <AuthGate>
        <BrowserRouter>
          <Routes>
            <Route element={<DashboardShell />}>
              <Route index element={<OverviewPage />} />
              <Route path="markets" element={<MarketsPage />} />
              <Route path="onchain" element={<OnchainPage />} />
              <Route path="mempool" element={<MempoolPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <WalletDrawer />
      </AuthGate>
      <LocaleToggle />
    </LocaleProvider>
  );
}
```

- [ ] **Step 3: Verify the build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: Manual smoke test**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173. Verify:

1. The `EN | DE` pill is visible bottom-right on every page (login, Overview, Markets, Onchain, Mempool).
2. `EN` is initially highlighted.
3. Click `DE`. The whole UI flips to German within a frame. Pill highlight moves.
4. Reload the page. UI stays in German. Pill still shows DE highlighted.
5. Click `EN`. UI flips back. Reload, stays English.
6. Open DevTools Application tab → Local Storage → confirm `etherscope.locale` is `"de"` or `"en"` matching the toggle state.
7. Open the wallet drawer (click any address). Confirm drawer copy is translated.
8. Open the alert form. Confirm form labels and placeholders are translated.

Stop the dev server when done.

- [ ] **Step 5: Update `CLAUDE.md`**

Open `CLAUDE.md` and find the `## UI polish` section. Add this entry at the end of the bulleted list (preserving the existing entries):

```
- German locale ✅ Floating EN/DE toggle (bottom-right pill) flips dashboard chrome + conversational copy between English and German via a custom React Context (no i18n library; flat TS dicts; type-safe via `keyof typeof en`). Persisted to `localStorage` (`etherscope.locale`). Excludes data values, asset symbols, DEX/CEX names, and crypto jargon (per `docs/i18n-glossary.md`). v1 is EN+DE only; adding more languages is a 1-day refactor to a real library. Spec: `docs/superpowers/specs/2026-05-11-german-translation-design.md`.
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/LocaleToggle.tsx frontend/src/App.tsx CLAUDE.md
git commit -m "feat(i18n): floating EN/DE toggle + wire LocaleProvider in App"
```

- [ ] **Step 7: Push the branch**

```bash
git push -u origin feature/german-translation
```

---

## Final verification

After all five tasks land, before merging to `main`:

1. **Compile-time guarantees** — `cd frontend && npm run build` exits 0. The TypeScript compile is the strongest contract: every `t()` call uses a known key, and every key in `en.ts` has a DE counterpart.

2. **Manual visual QA** — `cd frontend && npm run dev`, click through every page in both locales:
   - Overview: PriceHero, MarketRegime, SmartMoneyDirection, CexNetFlow, CategoryNetFlow tiles
   - Markets: PriceChart, Derivatives, Liquidations, SmartMoney, OrderFlow, VolumeStructure, OnchainPerps, MantleOrderFlow
   - Onchain: every section header + every panel
   - Mempool: MempoolPanel + AlertEventsPanel
   - Wallet drawer (click any address): smart-money tile, balance card, holdings, counterparties, linked wallets
   - Alert form: rule type dropdown options, parameter labels
   - Toast on alert fire (if you can trigger one)

3. **No-tests note for the merge PR description** — call out that this branch deliberately doesn't add a frontend test runner. The TypeScript type system enforces dict parity at compile time; runtime tests of the trivial `useT` lookup add infrastructure cost (vitest + jsdom + @testing-library) for marginal value. If a future feature needs tests, vitest can land separately.

4. **Merge** — once the German client has eyeballed the live deploy and confirmed the translations read naturally, merge `feature/german-translation` to `main` via the deploy workflow. Path filter detects `frontend/**` change → triggers full rebuild → frontend container picks up the new bundle. No backend or migration involvement.
