import { useEffect } from "react";

/** Fire a global custom event with this name to open the New Rule modal. */
export const NEW_RULE_EVENT = "etherscope:new-rule";

function isTypingInto(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

/** Single-key shortcuts, skipped while the user is editing text. */
export function useGlobalShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isTypingInto(e.target)) return;
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent(NEW_RULE_EVENT));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
