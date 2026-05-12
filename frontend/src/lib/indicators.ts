// Pure indicator math. All functions take a price series (typically the
// candle closes) and return a same-length array of numbers; positions
// before the indicator has enough samples are filled with NaN so chart
// libraries can skip them via `whitespaceData` semantics.

export function sma(values: number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (period <= 0 || values.length < period) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

export function ema(values: number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (period <= 0 || values.length < period) return out;
  const k = 2 / (period + 1);
  // Seed EMA with the SMA of the first `period` values.
  let seed = 0;
  for (let i = 0; i < period; i++) seed += values[i];
  let prev = seed / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    const v = values[i] * k + prev * (1 - k);
    out[i] = v;
    prev = v;
  }
  return out;
}

export type BollingerBands = {
  upper: number[];
  middle: number[];
  lower: number[];
};

export function bollinger(values: number[], period = 20, mult = 2): BollingerBands {
  const middle = sma(values, period);
  const upper = new Array<number>(values.length).fill(NaN);
  const lower = new Array<number>(values.length).fill(NaN);
  if (values.length < period) return { upper, middle, lower };
  for (let i = period - 1; i < values.length; i++) {
    const m = middle[i];
    let sq = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const d = values[j] - m;
      sq += d * d;
    }
    const sd = Math.sqrt(sq / period);
    upper[i] = m + mult * sd;
    lower[i] = m - mult * sd;
  }
  return { upper, middle, lower };
}

export function rsi(values: number[], period = 14): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (values.length < period + 1) return out;
  // Wilder's smoothing: seed avg gain/loss with simple mean over the first
  // `period` deltas, then exponential-smooth from there.
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const d = values[i] - values[i - 1];
    if (d >= 0) gains += d;
    else losses -= d;
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    const g = d > 0 ? d : 0;
    const l = d < 0 ? -d : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

export type MacdSeries = {
  macd: number[];
  signal: number[];
  hist: number[];
};

export function macd(
  values: number[],
  fast = 12,
  slow = 26,
  signalPeriod = 9,
): MacdSeries {
  const fastE = ema(values, fast);
  const slowE = ema(values, slow);
  const macdLine = values.map((_, i) =>
    Number.isFinite(fastE[i]) && Number.isFinite(slowE[i])
      ? fastE[i] - slowE[i]
      : NaN,
  );
  // Signal = EMA of macdLine, but only over the defined portion.
  const firstDefined = macdLine.findIndex((v) => Number.isFinite(v));
  let signal = new Array<number>(values.length).fill(NaN);
  if (firstDefined !== -1) {
    const defined = macdLine.slice(firstDefined);
    const signalDefined = ema(defined, signalPeriod);
    for (let i = 0; i < signalDefined.length; i++) {
      signal[firstDefined + i] = signalDefined[i];
    }
  }
  const hist = macdLine.map((m, i) =>
    Number.isFinite(m) && Number.isFinite(signal[i]) ? m - signal[i] : NaN,
  );
  return { macd: macdLine, signal, hist };
}
