import type { Timeframe } from "../api";
import Pill from "./ui/Pill";

const OPTIONS: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"];

type Props = {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
};

export default function TimeframeSelector({ value, onChange }: Props) {
  return <Pill value={value} onChange={onChange} options={OPTIONS} />;
}
