type Props = {
  values: number[];
  width?: number;
  height?: number;
  color?: "up" | "down" | "neutral";
  fill?: boolean;
};

const STROKE_BY_COLOR: Record<NonNullable<Props["color"]>, string> = {
  up: "rgb(34 197 94)",
  down: "rgb(239 68 68)",
  neutral: "rgb(148 163 184)",
};

const FILL_BY_COLOR: Record<NonNullable<Props["color"]>, string> = {
  up: "rgba(34, 197, 94, 0.18)",
  down: "rgba(239, 68, 68, 0.18)",
  neutral: "rgba(148, 163, 184, 0.18)",
};

export default function Sparkline({
  values,
  width = 80,
  height = 20,
  color = "neutral",
  fill = true,
}: Props) {
  const stroke = STROKE_BY_COLOR[color];
  const fillColor = FILL_BY_COLOR[color];

  if (values.length < 2) {
    return (
      <svg width={width} height={height} aria-hidden>
        <line
          x1={0}
          x2={width}
          y1={height / 2}
          y2={height / 2}
          stroke={stroke}
          strokeWidth={1}
          strokeOpacity={0.4}
        />
      </svg>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const padY = 2;
  const usableH = height - padY * 2;

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = padY + (1 - (v - min) / range) * usableH;
    return [x, y] as const;
  });

  const pathD = points
    .map(([x, y], i) => (i === 0 ? `M ${x},${y}` : `L ${x},${y}`))
    .join(" ");

  const areaD =
    pathD +
    ` L ${width},${height} L 0,${height} Z`;

  const crossesZero = min < 0 && max > 0;
  const zeroY = padY + (1 - (0 - min) / range) * usableH;

  return (
    <svg width={width} height={height} aria-hidden>
      {fill && (
        <path d={areaD} fill={fillColor} stroke="none" />
      )}
      {crossesZero && (
        <line
          x1={0}
          x2={width}
          y1={zeroY}
          y2={zeroY}
          stroke="rgb(100 116 139)"
          strokeWidth={0.5}
          strokeDasharray="2 2"
          strokeOpacity={0.5}
        />
      )}
      <path d={pathD} fill="none" stroke={stroke} strokeWidth={1.25} />
    </svg>
  );
}
