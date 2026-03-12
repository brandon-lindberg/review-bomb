"use client";

import { useState } from "react";

interface ExpandableTextProps {
  text: string;
  className?: string;
  collapsedLines?: number;
  collapseAfter?: number;
}

export function ExpandableText({
  text,
  className,
  collapsedLines = 4,
  collapseAfter = 320,
}: ExpandableTextProps) {
  const [expanded, setExpanded] = useState(false);
  const normalized = text.replace(/\s+/g, " ").trim();

  if (!normalized) return null;

  const shouldCollapse = normalized.length > collapseAfter;

  return (
    <div>
      <p
        className={className}
        style={!expanded && shouldCollapse
          ? {
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: collapsedLines,
              overflow: "hidden",
            }
          : undefined}
      >
        {normalized}
      </p>
      {shouldCollapse && (
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
          className="mt-2 text-sm font-medium cursor-pointer hover:opacity-80"
          style={{ color: "var(--color-rust)" }}
        >
          {expanded ? "See less" : "See more"}
        </button>
      )}
    </div>
  );
}
