import { useId, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { PricePoint } from "../api/types";
import { useElementWidth } from "../hooks/useElementWidth";
import {
  areaPath,
  axisLabel,
  axisPrice,
  labelIndices,
  linePath,
  nearestIndex,
  niceTicks,
  plotHeight,
  plotWidth,
  xAt,
  yAt,
  yDomain,
  type Box,
  type ChartRange,
} from "../lib/chart";
import { directionOf, formatChangePct, formatLongDate, formatPrice, formatVolume } from "../lib/format";

interface Props {
  symbol: string;
  range: ChartRange;
  points: PricePoint[]; // needs at least two
}

const HEIGHT = 280;

/**
 * A line chart of closing prices, drawn as SVG at its real pixel width.
 * Hover (or arrow keys when focused) picks a day; the readout above the chart says what it is.
 */
export function PriceChart({ symbol, range, points }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const readoutId = useId();

  const n = points.length;
  const closes = points.map((p) => p.close);
  const box: Box = { width, height: HEIGHT, left: width < 480 ? 44 : 54, right: 12, top: 10, bottom: 26 };
  const domain = yDomain(closes);
  const yTicks = niceTicks(domain[0], domain[1], 5);
  const xLabels = labelIndices(n, width < 480 ? 3 : 5);

  const index = Math.min(active ?? n - 1, n - 1);
  const selected = points[index];
  const sinceStart = (selected.close / points[0].close - 1) * 100;
  const tone = closes[n - 1] >= closes[0] ? "up" : "down";

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    const left = event.currentTarget.getBoundingClientRect().left;
    setActive(nearestIndex(event.clientX - left, n, box));
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 10 : 1;
    const moves: Record<string, number> = {
      ArrowLeft: Math.max(0, index - step),
      ArrowRight: Math.min(n - 1, index + step),
      Home: 0,
      End: n - 1,
    };
    if (event.key in moves) {
      event.preventDefault();
      setActive(moves[event.key]);
    }
  }

  const summary = `${symbol} closing price over ${range}: from ${formatPrice(points[0].close)} to ${formatPrice(closes[n - 1])}`;

  return (
    <div>
      <p id={readoutId} className="readout" role="status">
        <strong>{formatLongDate(selected.date)}</strong>
        <span>{formatPrice(selected.close)}</span>
        <span className={directionOf(sinceStart)}>{formatChangePct(sinceStart)} since {formatLongDate(points[0].date)}</span>
        <span className="muted">Volume {formatVolume(selected.volume)}</span>
      </p>

      <div
        ref={ref}
        className="chart-wrap"
        tabIndex={0}
        role="group"
        aria-label={`${symbol} price chart. Use the left and right arrow keys to move between days.`}
        aria-describedby={readoutId}
        onKeyDown={onKeyDown}
        onBlur={() => setActive(null)}
      >
        <svg
          className={`chart ${tone}`}
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="img"
          aria-label={summary}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setActive(null)}
        >
          {yTicks.map((tick) => {
            const y = yAt(tick, domain, box);
            return (
              <g key={tick}>
                <line className="grid" x1={box.left} x2={width - box.right} y1={y} y2={y} />
                <text className="axis" x={box.left - 6} y={y} textAnchor="end" dominantBaseline="middle">
                  {axisPrice(tick)}
                </text>
              </g>
            );
          })}

          {xLabels.map((i, k) => (
            <text
              key={i}
              className="axis"
              x={xAt(i, n, box)}
              y={HEIGHT - 6}
              textAnchor={k === 0 ? "start" : k === xLabels.length - 1 ? "end" : "middle"}
            >
              {axisLabel(points[i].date, range)}
            </text>
          ))}

          <path className="area" d={areaPath(closes, domain, box)} />
          <path className="line" d={linePath(closes, domain, box)} fill="none" />

          {active !== null && (
            <line
              className="guide"
              x1={xAt(index, n, box)}
              x2={xAt(index, n, box)}
              y1={box.top}
              y2={box.top + plotHeight(box)}
            />
          )}
          <circle className="dot" cx={xAt(index, n, box)} cy={yAt(selected.close, domain, box)} r={4} />
          <rect x={box.left} y={box.top} width={plotWidth(box)} height={plotHeight(box)} fill="transparent" />
        </svg>
      </div>
    </div>
  );
}
