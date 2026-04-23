import type { FlowRange } from "../api";
import Pill from "./ui/Pill";

type Props = {
  value: FlowRange;
  onChange: (r: FlowRange) => void;
  options?: FlowRange[];
};

const DEFAULT_OPTIONS: FlowRange[] = ["24h", "48h", "7d", "30d"];

export default function FlowRangeSelector({ value, onChange, options = DEFAULT_OPTIONS }: Props) {
  return <Pill size="xs" value={value} onChange={onChange} options={options} />;
}
