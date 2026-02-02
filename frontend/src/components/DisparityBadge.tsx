"use client";

import {
  getDisparityColor,
  getDisparityBgColor,
  getDisparityLabel,
  getDisparityLevel,
  formatDisparity,
} from "@/lib/disparity-colors";

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

  const level = getDisparityLevel(disparity);
  const color = getDisparityColor(disparity);
  const bgColor = getDisparityBgColor(disparity);

  // Use solid background for high/extreme, transparent for aligned/moderate
  const style: React.CSSProperties =
    level === "high" || level === "extreme"
      ? { backgroundColor: color, color: "white" }
      : { backgroundColor: bgColor, color: color };

  const sizeClasses = {
    sm: "px-1.5 py-0.5 text-xs",
    md: "px-2 py-1 text-sm",
    lg: "px-3 py-1.5 text-base font-semibold",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${sizeClasses[size]}`}
      style={style}
      title={getDisparityLabel(disparity)}
    >
      {formatDisparity(disparity)}
    </span>
  );
}
