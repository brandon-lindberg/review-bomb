"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";

interface ExpandableTextProps {
  text: string;
  className?: string;
  collapsedLines?: number;
}

export function ExpandableText({
  text,
  className,
  collapsedLines = 4,
}: ExpandableTextProps) {
  const [expanded, setExpanded] = useState(false);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const fullMeasureRef = useRef<HTMLParagraphElement | null>(null);
  const collapsedMeasureRef = useRef<HTMLParagraphElement | null>(null);
  const normalized = text.replace(/\s+/g, " ").trim();

  useEffect(() => {
    if (!normalized || typeof window === "undefined") {
      return;
    }

    const measureOverflow = () => {
      const fullHeight = fullMeasureRef.current?.getBoundingClientRect().height ?? 0;
      const collapsedHeight = collapsedMeasureRef.current?.getBoundingClientRect().height ?? 0;
      setIsOverflowing(fullHeight - collapsedHeight > 1);
    };

    const animationFrame = window.requestAnimationFrame(measureOverflow);

    if (!wrapperRef.current || typeof ResizeObserver === "undefined") {
      return () => {
        window.cancelAnimationFrame(animationFrame);
      };
    }

    const observer = new ResizeObserver(() => {
      window.requestAnimationFrame(measureOverflow);
    });

    observer.observe(wrapperRef.current);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      observer.disconnect();
    };
  }, [className, collapsedLines, normalized]);

  if (!normalized) return null;

  const collapsedStyle: CSSProperties = {
    display: "-webkit-box",
    WebkitBoxOrient: "vertical",
    WebkitLineClamp: collapsedLines,
    overflow: "hidden",
  };

  return (
    <div ref={wrapperRef} className="relative">
      <div
        aria-hidden="true"
        className="pointer-events-none invisible absolute left-0 top-0 w-full"
      >
        <p ref={fullMeasureRef} className={className}>
          {normalized}
        </p>
        <p
          ref={collapsedMeasureRef}
          className={className}
          style={collapsedStyle}
        >
          {normalized}
        </p>
      </div>
      <p
        className={className}
        style={!expanded ? collapsedStyle : undefined}
      >
        {normalized}
      </p>
      {isOverflowing && (
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
