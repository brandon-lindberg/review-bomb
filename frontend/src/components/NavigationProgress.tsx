"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { NAVIGATION_START_EVENT } from "@/lib/navigation-progress";

const MAX_PROGRESS_BEFORE_COMPLETE = 92;
const TICK_MS = 120;
const COMPLETE_HIDE_DELAY_MS = 180;
const STUCK_RESET_MS = 15000;

export function NavigationProgress() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const routeKey = `${pathname}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;

  const routeKeyRef = useRef(routeKey);
  const inFlightRef = useRef(false);
  const tickTimerRef = useRef<number | null>(null);
  const hideTimerRef = useRef<number | null>(null);
  const stuckTimerRef = useRef<number | null>(null);

  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(0);

  const clearTick = useCallback(() => {
    if (tickTimerRef.current != null) {
      window.clearInterval(tickTimerRef.current);
      tickTimerRef.current = null;
    }
  }, []);

  const clearHide = useCallback(() => {
    if (hideTimerRef.current != null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const clearStuck = useCallback(() => {
    if (stuckTimerRef.current != null) {
      window.clearTimeout(stuckTimerRef.current);
      stuckTimerRef.current = null;
    }
  }, []);

  const startProgress = useCallback(() => {
    clearHide();
    clearStuck();

    if (!inFlightRef.current) {
      inFlightRef.current = true;
      setVisible(true);
      setProgress((prev) => (prev > 8 ? prev : 12));
    }

    if (tickTimerRef.current == null) {
      tickTimerRef.current = window.setInterval(() => {
        setProgress((prev) => {
          if (prev >= MAX_PROGRESS_BEFORE_COMPLETE) return prev;
          const remaining = MAX_PROGRESS_BEFORE_COMPLETE - prev;
          const step = Math.max(1.5, remaining * 0.12);
          return Math.min(MAX_PROGRESS_BEFORE_COMPLETE, prev + step);
        });
      }, TICK_MS);
    }

    stuckTimerRef.current = window.setTimeout(() => {
      inFlightRef.current = false;
      clearTick();
      setProgress(100);
      hideTimerRef.current = window.setTimeout(() => {
        setVisible(false);
        setProgress(0);
      }, COMPLETE_HIDE_DELAY_MS);
    }, STUCK_RESET_MS);
  }, [clearHide, clearStuck, clearTick]);

  const finishProgress = useCallback(() => {
    inFlightRef.current = false;
    clearTick();
    clearStuck();
    clearHide();

    setVisible(true);
    setProgress(100);
    hideTimerRef.current = window.setTimeout(() => {
      setVisible(false);
      setProgress(0);
    }, COMPLETE_HIDE_DELAY_MS);
  }, [clearHide, clearStuck, clearTick]);

  useEffect(() => {
    if (routeKeyRef.current !== routeKey) {
      routeKeyRef.current = routeKey;
      const timer = window.setTimeout(() => {
        finishProgress();
      }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [routeKey, finishProgress]);

  useEffect(() => {
    const handleNavigationStart = () => {
      startProgress();
    };

    const handlePopState = () => {
      startProgress();
    };

    const handleDocumentClick = (event: MouseEvent) => {
      if (event.defaultPrevented) return;
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const target = event.target;
      if (!(target instanceof Element)) return;

      const anchor = target.closest("a");
      if (!anchor) return;
      if (anchor.hasAttribute("download")) return;
      if (anchor.target && anchor.target !== "_self") return;

      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#")) return;

      let url: URL;
      try {
        url = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }

      if (url.origin !== window.location.origin) return;
      if (!url.pathname.startsWith("/")) return;

      const nextRouteKey = `${url.pathname}${url.search}`;
      if (nextRouteKey === routeKeyRef.current) return;

      startProgress();
    };

    window.addEventListener(NAVIGATION_START_EVENT, handleNavigationStart);
    window.addEventListener("popstate", handlePopState);
    document.addEventListener("click", handleDocumentClick, true);

    return () => {
      window.removeEventListener(NAVIGATION_START_EVENT, handleNavigationStart);
      window.removeEventListener("popstate", handlePopState);
      document.removeEventListener("click", handleDocumentClick, true);
      clearTick();
      clearHide();
      clearStuck();
    };
  }, [startProgress, clearTick, clearHide, clearStuck]);

  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none fixed inset-x-0 top-0 z-[100] h-1 transition-opacity duration-200 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <div
        className="h-full transition-[width] duration-150 ease-out"
        style={{
          width: `${progress}%`,
          background:
            "linear-gradient(90deg, var(--color-rust) 0%, var(--color-orange) 55%, var(--color-tan) 100%)",
          boxShadow: "0 0 10px rgba(187, 59, 14, 0.45)",
        }}
      />
    </div>
  );
}
