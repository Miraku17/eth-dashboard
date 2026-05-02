export type PegCurrency = "USD" | "EUR" | "GBP" | "CHF" | "SGD" | "BRL" | "OTHER";

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
  USDe: "USD",
  XSGD: "SGD",
  BRZ: "BRL",
};

export const PEG_ORDER: PegCurrency[] = ["USD", "EUR", "GBP", "CHF", "SGD", "BRL", "OTHER"];

export function pegOf(asset: string): PegCurrency {
  return PEG_BY_ASSET[asset] ?? "OTHER";
}
