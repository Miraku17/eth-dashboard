import Pill from "./ui/Pill";

export type ChartType = "candles" | "line" | "area" | "baseline";

const OPTIONS: { value: ChartType; label: string }[] = [
  { value: "candles", label: "Candles" },
  { value: "line", label: "Line" },
  { value: "area", label: "Area" },
  { value: "baseline", label: "Baseline" },
];

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
  return <Pill size="xs" value={value} onChange={onChange} options={OPTIONS} />;
}
