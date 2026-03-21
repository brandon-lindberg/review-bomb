import { buildSparklinePath, formatCompactPlayerCount } from "@/lib/player-count-chart";

interface MiniPlayerCountChartProps {
  values: number[];
  color?: string;
  className?: string;
  ariaLabel?: string;
}

const VIEWBOX_WIDTH = 220;
const VIEWBOX_HEIGHT = 84;

export function MiniPlayerCountChart({
  values,
  color = "var(--color-rust)",
  className = "",
  ariaLabel = "Player count trend",
}: MiniPlayerCountChartProps) {
  if (values.length < 2) {
    return (
      <div
        className={`flex h-20 w-full items-center justify-center rounded-xl border border-dashed text-xs text-gray-400 ${className}`.trim()}
        style={{ borderColor: "var(--border)" }}
      >
        Not enough data
      </div>
    );
  }

  const path = buildSparklinePath(values, VIEWBOX_WIDTH, VIEWBOX_HEIGHT - 8, 8);
  const latestValue = values[values.length - 1];
  const maxValue = Math.max(...values);
  const latestX = VIEWBOX_WIDTH - 8;
  const latestY = (() => {
    const minValue = Math.min(...values);
    const valueRange = maxValue - minValue || 1;
    const usableHeight = (VIEWBOX_HEIGHT - 8) - 16;
    const normalized = (latestValue - minValue) / valueRange;
    return 8 + usableHeight - normalized * usableHeight;
  })();

  return (
    <div className={`space-y-2 ${className}`.trim()}>
      <div className="flex items-center justify-end gap-3 text-[11px]">
        <div className="min-w-0 text-right">
          <div className="font-medium text-gray-500">Now</div>
          <div className="font-semibold text-gray-900">{formatCompactPlayerCount(latestValue)}</div>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
        className="h-16 w-full"
        fill="none"
        role="img"
        aria-label={ariaLabel}
      >
        <title>{`${ariaLabel}, latest ${latestValue.toLocaleString()} players`}</title>
        <path
          d={`M 8 ${VIEWBOX_HEIGHT - 12} H ${VIEWBOX_WIDTH - 8}`}
          stroke="var(--border)"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d={path}
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle
          cx={latestX}
          cy={latestY}
          r="4.5"
          fill="var(--background-card)"
          stroke={color}
          strokeWidth="2.5"
        />
      </svg>
    </div>
  );
}
