export type PegCurrency = "USD" | "EUR" | "GBP" | "CHF" | "OTHER";

export const PEG_BY_ASSET: Record<string, PegCurrency> = {
  USDT: "USD",
  USDC: "USD",
  DAI: "USD",
  PYUSD: "USD",
  FDUSD: "USD",
  USDS: "USD",
  GHO: "USD",
  EUROC: "EUR",
  EURCV: "EUR",
  EURe: "EUR",
  ZCHF: "CHF",
  tGBP: "GBP",
};

export const PEG_ORDER: PegCurrency[] = ["USD", "EUR", "GBP", "CHF", "OTHER"];

export function pegOf(asset: string): PegCurrency {
  return PEG_BY_ASSET[asset] ?? "OTHER";
}
