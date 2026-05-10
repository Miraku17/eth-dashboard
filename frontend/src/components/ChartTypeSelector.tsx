import { useT } from "../i18n/LocaleProvider";
import type { TranslationKey } from "../i18n/types";

import Pill from "./ui/Pill";

export type ChartType = "candles" | "line" | "area" | "baseline";

const VALUES: ChartType[] = ["candles", "line", "area", "baseline"];

const LABEL_KEYS: Record<ChartType, TranslationKey> = {
  candles: "chart_type.candles",
  line: "chart_type.line",
  area: "chart_type.area",
  baseline: "chart_type.baseline",
};

type Props = {
  value: ChartType;
  onChange: (t: ChartType) => void;
};

/**
 * Chart-type toggle group for the price panel. Mirrors the
 * TimeframeSelector pattern (same Pill component) so the actions row
 * reads as a single coherent unit.
 *
 * baseline = area chart with the period's first close as the zero line:
 *   green tint above (price up vs period start), red tint below
 *   (price down). Useful for "where are we vs where we started" at a
 *   glance — distinct enough from line/area to be worth its own option.
 */
export default function ChartTypeSelector({ value, onChange }: Props) {
  const t = useT();
  const options = VALUES.map((v) => ({ value: v, label: t(LABEL_KEYS[v]) }));
  return <Pill size="xs" value={value} onChange={onChange} options={options} />;
}
