import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn-style class joiner. Combines `clsx` (conditional class handling)
 * with `tailwind-merge` (last-wins resolution for conflicting Tailwind
 * utility classes, e.g. `px-2 px-4` → `px-4`).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
