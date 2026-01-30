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

  // Color based on disparity magnitude
  let bgColor = "bg-gray-100 text-gray-700";
  if (Math.abs(value) >= 15) {
    bgColor = isPositive
      ? "bg-red-100 text-red-800"
      : "bg-blue-100 text-blue-800";
  } else if (Math.abs(value) >= 10) {
    bgColor = isPositive
      ? "bg-orange-100 text-orange-800"
      : "bg-cyan-100 text-cyan-800";
  } else if (Math.abs(value) >= 5) {
    bgColor = isPositive
      ? "bg-yellow-100 text-yellow-800"
      : "bg-teal-100 text-teal-800";
  } else {
    bgColor = "bg-green-100 text-green-800";
  }

  const sizeClasses = {
    sm: "px-1.5 py-0.5 text-xs",
    md: "px-2 py-1 text-sm",
    lg: "px-3 py-1.5 text-base font-semibold",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${bgColor} ${sizeClasses[size]}`}
      title={`Critics scored ${isPositive ? "higher" : isNegative ? "lower" : "same as"} users`}
    >
      {isPositive ? "+" : isNegative ? "" : ""}
      {absValue}
    </span>
  );
}
