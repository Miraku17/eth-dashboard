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
