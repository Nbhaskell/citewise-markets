interface Props {
  values: number[];
  label: string;
  width?: number;
  height?: number;
}

/** A tiny line chart drawn as plain SVG. Green if the last value is at or above the first, red if below. */
export function Sparkline({ values, label, width = 96, height = 28 }: Props) {
  if (values.length < 2) return <span className="muted" aria-label={`${label}: not enough data`}>–</span>;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 2;
  const points = values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (width - pad * 2);
      const y = pad + (1 - (v - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const tone = values[values.length - 1] >= values[0] ? "up" : "down";

  return (
    <svg className={`sparkline ${tone}`} width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <polyline points={points} fill="none" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
