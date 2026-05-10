import type { en } from "./en";

export type Locale = "en" | "de";
export type TranslationKey = keyof typeof en;
