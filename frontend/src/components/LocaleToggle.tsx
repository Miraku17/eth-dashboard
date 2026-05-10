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
