/**
 * Centralized per-asset color palette. The same asset gets the same color
 * everywhere — Recharts charts, sparklines, asset badges, legends.
 *
 * Two parallel lookups are exposed because the dashboard uses two color
 * systems:
 *   - `rgb`           — raw "rgb(R G B)" strings, for SVG strokes/fills
 *                       (Recharts <Area>, sparkline paths, legend dots).
 *   - `badgeClasses`  — Tailwind utility class strings for AssetBadge
 *                       (bg + text + ring), used in WhaleTransfersPanel +
 *                       MempoolPanel.
 *
 * Stable note: LST tokens and stables never coexist in the same chart, so
 * a few palette colors are reused across both groups (e.g., sky for both
 * USDC and stETH). That's intentional — keeps the palette tight.
 */

export type AssetColor = {
  rgb: string;
  badgeClasses: string;
};

const FALLBACK: AssetColor = {
  rgb: "rgb(148 163 184)", // slate-400
  badgeClasses: "bg-surface-raised text-slate-300 ring-surface-border",
};

export const ASSET_COLOR: Record<string, AssetColor> = {
  // Native ETH
  ETH: {
    rgb: "rgb(99 102 241)", // indigo-500 (matches `brand` token)
    badgeClasses: "bg-brand/15 text-brand-soft ring-brand/20",
  },

  // USD stables
  USDT: {
    rgb: "rgb(34 197 94)", // green-500
    badgeClasses: "bg-up/10 text-up ring-up/20",
  },
  USDC: {
    rgb: "rgb(56 189 248)", // sky-400
    badgeClasses: "bg-sky-500/10 text-sky-300 ring-sky-400/20",
  },
  DAI: {
    rgb: "rgb(251 191 36)", // amber-400
    badgeClasses: "bg-amber-500/10 text-amber-300 ring-amber-400/20",
  },
  PYUSD: {
    rgb: "rgb(168 85 247)", // purple-500
    badgeClasses: "bg-purple-500/10 text-purple-300 ring-purple-400/20",
  },
  FDUSD: {
    rgb: "rgb(250 204 21)", // yellow-400
    badgeClasses: "bg-yellow-500/10 text-yellow-300 ring-yellow-400/20",
  },
  USDS: {
    rgb: "rgb(99 102 241)", // indigo-500
    badgeClasses: "bg-indigo-500/10 text-indigo-300 ring-indigo-400/20",
  },
  GHO: {
    rgb: "rgb(20 184 166)", // teal-500
    badgeClasses: "bg-teal-500/10 text-teal-300 ring-teal-400/20",
  },
  USDe: {
    rgb: "rgb(244 114 182)", // pink-400
    badgeClasses: "bg-pink-500/10 text-pink-300 ring-pink-400/20",
  },

  // EUR stables
  EUROC: {
    rgb: "rgb(96 165 250)", // blue-400
    badgeClasses: "bg-blue-500/10 text-blue-300 ring-blue-400/20",
  },
  EURCV: {
    rgb: "rgb(167 139 250)", // violet-400
    badgeClasses: "bg-violet-500/10 text-violet-300 ring-violet-400/20",
  },
  EURe: {
    rgb: "rgb(52 211 153)", // emerald-400
    badgeClasses: "bg-emerald-500/10 text-emerald-300 ring-emerald-400/20",
  },
  EURS: {
    rgb: "rgb(56 189 248)", // sky-400
    badgeClasses: "bg-sky-500/10 text-sky-300 ring-sky-400/20",
  },

  // Other currency stables
  ZCHF: {
    rgb: "rgb(248 113 113)", // red-400
    badgeClasses: "bg-red-500/10 text-red-300 ring-red-400/20",
  },
  tGBP: {
    rgb: "rgb(251 146 60)", // orange-400
    badgeClasses: "bg-orange-500/10 text-orange-300 ring-orange-400/20",
  },
  XSGD: {
    rgb: "rgb(232 121 249)", // fuchsia-400
    badgeClasses: "bg-fuchsia-500/10 text-fuchsia-300 ring-fuchsia-400/20",
  },
  BRZ: {
    rgb: "rgb(132 204 22)", // lime-500
    badgeClasses: "bg-lime-500/10 text-lime-300 ring-lime-400/20",
  },

  // Liquid staking tokens (chart-only — no badge sites)
  stETH: {
    rgb: "rgb(56 189 248)", // sky-400 (mirrors USDC; never co-charted)
    badgeClasses: "bg-sky-500/10 text-sky-300 ring-sky-400/20",
  },
  rETH: {
    rgb: "rgb(244 114 182)", // pink-400
    badgeClasses: "bg-pink-500/10 text-pink-300 ring-pink-400/20",
  },
  cbETH: {
    rgb: "rgb(96 165 250)", // blue-400
    badgeClasses: "bg-blue-500/10 text-blue-300 ring-blue-400/20",
  },
  sfrxETH: {
    rgb: "rgb(251 146 60)", // orange-400
    badgeClasses: "bg-orange-500/10 text-orange-300 ring-orange-400/20",
  },
  mETH: {
    rgb: "rgb(52 211 153)", // emerald-400
    badgeClasses: "bg-emerald-500/10 text-emerald-300 ring-emerald-400/20",
  },
  swETH: {
    rgb: "rgb(167 139 250)", // violet-400
    badgeClasses: "bg-violet-500/10 text-violet-300 ring-violet-400/20",
  },
  ETHx: {
    rgb: "rgb(250 204 21)", // yellow-400
    badgeClasses: "bg-yellow-500/10 text-yellow-300 ring-yellow-400/20",
  },
};

export function colorOf(asset: string): AssetColor {
  return ASSET_COLOR[asset] ?? FALLBACK;
}

export function rgbOf(asset: string): string {
  return colorOf(asset).rgb;
}

export function badgeOf(asset: string): string {
  return colorOf(asset).badgeClasses;
}
