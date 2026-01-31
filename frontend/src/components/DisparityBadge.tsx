"use client";

interface DisparityBadgeProps {
  disparity: number | null | undefined;
  size?: "sm" | "md" | "lg";
}

export function DisparityBadge({
  disparity,
  size = "md",
}: DisparityBadgeProps) {
  if (disparity == null) {
    return <span className="text-gray-400 text-sm">N/A</span>;
  }

  const value = disparity;
  const isPositive = value > 0;
  const isNegative = value < 0;
  const absValue = Math.abs(value).toFixed(1);

  // Color based on disparity magnitude using brand palette
  // Positive = critics rated higher than users (rust/orange)
  // Negative = critics rated lower than users (sage green)
  // Neutral = aligned with users (tan)
  let style: React.CSSProperties = {};
  let className = "";

  if (Math.abs(value) >= 15) {
    // High disparity
    style = isPositive
      ? { backgroundColor: "#BB3B0E", color: "white" }  // rust
      : { backgroundColor: "#708160", color: "white" }; // sage
  } else if (Math.abs(value) >= 10) {
    // Medium-high disparity
    style = isPositive
      ? { backgroundColor: "#DD7631", color: "white" }  // orange
      : { backgroundColor: "#708160", color: "white" }; // sage
  } else if (Math.abs(value) >= 5) {
    // Medium disparity
    style = isPositive
      ? { backgroundColor: "rgba(221, 118, 49, 0.2)", color: "#BB3B0E" }  // light orange bg
      : { backgroundColor: "rgba(112, 129, 96, 0.2)", color: "#708160" }; // light sage bg
  } else {
    // Low disparity - well aligned
    style = { backgroundColor: "rgba(216, 197, 147, 0.3)", color: "#5C574F" }; // tan bg
  }

  const sizeClasses = {
    sm: "px-1.5 py-0.5 text-xs",
    md: "px-2 py-1 text-sm",
    lg: "px-3 py-1.5 text-base font-semibold",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${sizeClasses[size]}`}
      style={style}
      title={`Critics scored ${isPositive ? "higher" : isNegative ? "lower" : "same as"} users`}
    >
      {isPositive ? "+" : isNegative ? "" : ""}
      {absValue}
    </span>
  );
}
