"use client";

import { useState, useCallback, useEffect, useRef, useTransition } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { emitNavigationStart } from "@/lib/navigation-progress";

interface SearchInputProps {
  defaultValue?: string;
  placeholder?: string;
  paramName?: string;
  debounceMs?: number;
}

export function SearchInput({
  defaultValue = "",
  placeholder = "Search...",
  paramName = "search",
  debounceMs = 400,
}: SearchInputProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [value, setValue] = useState(defaultValue);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const previousValueRef = useRef(defaultValue);
  const inputRef = useRef<HTMLInputElement>(null);

  // Perform the search by updating the URL without full page reload
  const performSearch = useCallback(
    (searchValue: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (searchValue.trim() && searchValue.trim().length >= 2) {
        params.set(paramName, searchValue.trim());
      } else {
        params.delete(paramName);
      }
      params.delete("page");
      
      const newUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
      emitNavigationStart();
      startTransition(() => {
        router.replace(newUrl, { scroll: false });
      });
    },
    [paramName, pathname, router, searchParams, startTransition]
  );

  // Debounced search effect - only triggers when value actually changes from user input
  useEffect(() => {
    // Only proceed if value actually changed (not just from URL/props change)
    if (value === previousValueRef.current) {
      return;
    }
    
    // Update previous value
    previousValueRef.current = value;

    // Clear existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Only search if value is empty (clear) or has 2+ characters
    if (value === "" || value.length >= 2) {
      debounceTimerRef.current = setTimeout(() => {
        performSearch(value);
      }, debounceMs);
    }

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [value, debounceMs, performSearch]);

  const handleClear = useCallback(() => {
    setValue("");
    previousValueRef.current = ""; // Update ref to prevent duplicate search
    // Immediately clear without debounce
    const params = new URLSearchParams(searchParams.toString());
    params.delete(paramName);
    params.delete("page");
    const newUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    emitNavigationStart();
    startTransition(() => {
      router.replace(newUrl, { scroll: false });
    });
    // Keep focus on input
    inputRef.current?.focus();
  }, [paramName, pathname, router, searchParams, startTransition]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      // Cancel any pending debounce and search immediately
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      previousValueRef.current = value; // Update ref to prevent duplicate search
      performSearch(value);
    },
    [value, performSearch]
  );

  return (
    <form onSubmit={handleSubmit} className="relative w-full" aria-busy={isPending}>
      <div className="relative">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400"
        >
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          className="site-field w-full pl-11 pr-14 py-3 text-sm focus:outline-none"
          aria-busy={isPending}
        />
        {isPending && (
          <span
            aria-hidden="true"
            className="absolute right-8 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin rounded-full border-2 border-solid border-t-transparent"
            style={{ borderColor: "var(--foreground-muted)", borderTopColor: "transparent" }}
          />
        )}
        {value && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-1 text-gray-400 hover:text-gray-600 disabled:opacity-60"
            aria-label="Clear search"
            disabled={isPending}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        )}
      </div>
    </form>
  );
}
