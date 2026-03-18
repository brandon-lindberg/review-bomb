"use client";

import Image from "next/image";
import { useState, useEffect, useRef, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { GameAvatar } from "@/components/GameAvatar";
import type { Game, Journalist, Outlet } from "@/types";

interface SelectedItem {
  id: number;
  name: string;
  image_url: string | null;
}

interface CompareSelectorProps {
  type: "journalists" | "outlets" | "games";
  selectedIds: number[];
  selectedItems: SelectedItem[];
  maxSelections: number;
}

interface SearchResult {
  id: number;
  name: string;
  image_url: string | null;
  review_count?: number;
}

export function CompareSelector({
  type,
  selectedIds,
  selectedItems,
  maxSelections,
}: CompareSelectorProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isNavigating, startTransition] = useTransition();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Search for items
  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      return;
    }

    const searchTimeout = setTimeout(async () => {
      setIsLoading(true);
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
        const response = await fetch(
          `${apiUrl}/search?q=${encodeURIComponent(query)}&limit=10`
        );
        if (response.ok) {
          const data = await response.json();
          const items: SearchResult[] =
            type === "journalists"
              ? data.journalists.map((j: Journalist) => ({
                  id: j.id,
                  name: j.name,
                  image_url: j.image_url,
                  review_count: j.review_count,
                }))
              : type === "outlets"
                ? data.outlets.map((o: Outlet) => ({
                    id: o.id,
                    name: o.name,
                    image_url: o.logo_url,
                    review_count: o.review_count,
                  }))
                : data.games.map((g: Game) => ({
                    id: g.id,
                    name: g.title,
                    image_url: g.image_url,
                    review_count: g.critic_review_count,
                  }));
          // Filter out already selected items
          setResults(items.filter((item) => !selectedIds.includes(item.id)));
        }
      } catch (error) {
        console.error("Search error:", error);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(searchTimeout);
  }, [query, type, selectedIds]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const navigateWithSelection = (nextIds: number[]) => {
    const params = new URLSearchParams(searchParams.toString());
    if (nextIds.length > 0) {
      params.set("ids", nextIds.join(","));
    } else {
      params.delete("ids");
    }
    params.set("type", type);
    const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    startTransition(() => {
      router.replace(nextUrl, { scroll: false });
    });
  };

  const handleSelect = (item: SearchResult) => {
    if (selectedIds.length >= maxSelections || isNavigating) return;

    const newIds = [...selectedIds, item.id];
    setShowDropdown(false);
    setQuery("");
    navigateWithSelection(newIds);
  };

  const handleRemove = (id: number) => {
    if (isNavigating) return;
    const newIds = selectedIds.filter((selectedId) => selectedId !== id);
    navigateWithSelection(newIds);
  };

  return (
    <div className="relative z-20 space-y-4 overflow-visible">
      {/* Search Input */}
      {selectedIds.length < maxSelections && (
        <div className="relative overflow-visible" ref={dropdownRef}>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setShowDropdown(true)}
            placeholder={`Search ${type}...`}
            className="site-field w-full px-4 py-3 outline-none disabled:opacity-70"
            disabled={isNavigating}
            aria-busy={isNavigating}
          />

          {/* Dropdown */}
          {showDropdown && (query.length >= 2 || isLoading) && (
            <div className="absolute left-0 right-0 top-full z-30 mt-2 max-h-72 overflow-y-auto rounded-[1.25rem] bg-white shadow-lg">
              {isLoading ? (
                <div className="px-4 py-4 text-sm text-gray-500">Searching...</div>
              ) : results.length > 0 ? (
                results.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleSelect(item)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50 disabled:opacity-70"
                    disabled={isNavigating}
                  >
                    {type === "games" ? (
                      <GameAvatar
                        title={item.name}
                        imageUrl={item.image_url}
                        width={48}
                        height={28}
                        sizes="48px"
                        className="h-7 w-12 rounded-lg object-contain"
                      />
                    ) : item.image_url ? (
                      <Image
                        src={item.image_url}
                        alt={item.name}
                        width={32}
                        height={32}
                        sizes="32px"
                        className="w-8 h-8 rounded-full object-cover"
                      />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
                        <span className="text-gray-500 text-sm font-medium">
                          {item.name.charAt(0)}
                        </span>
                      </div>
                    )}
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900">{item.name}</p>
                      {item.review_count !== undefined && (
                        <p className="text-sm text-gray-500">
                          {item.review_count} reviews
                        </p>
                      )}
                    </div>
                  </button>
                ))
              ) : query.length >= 2 ? (
                <div className="px-4 py-4 text-sm text-gray-500">No results found</div>
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* Selected Items */}
      {selectedItems.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedItems.map((item) => (
            <span
              key={item.id}
              className="inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm"
              style={{
                borderColor: "color-mix(in srgb, var(--color-rust) 20%, transparent)",
                backgroundColor: "color-mix(in srgb, var(--background-card-strong) 86%, var(--color-rust) 14%)",
                color: "var(--foreground)",
              }}
            >
              {type === "games" ? (
                <GameAvatar
                  title={item.name}
                  imageUrl={item.image_url}
                  width={28}
                  height={16}
                  sizes="28px"
                  className="h-4 w-7 rounded-md object-contain"
                />
              ) : item.image_url ? (
                <Image
                  src={item.image_url}
                  alt={item.name}
                  width={20}
                  height={20}
                  sizes="20px"
                  className="w-5 h-5 rounded-full object-cover"
                />
              ) : (
                <span
                  className="flex h-5 w-5 items-center justify-center rounded-full text-xs font-medium"
                  style={{ backgroundColor: "rgba(187, 59, 14, 0.16)", color: "var(--color-rust)" }}
                >
                  {item.name.charAt(0)}
                </span>
              )}
              <span className="font-medium">{item.name}</span>
              <button
                onClick={() => handleRemove(item.id)}
                className="transition-colors hover:text-rust disabled:opacity-60"
                aria-label="Remove"
                disabled={isNavigating}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Helper Text */}
      <p className="text-sm text-gray-500" aria-live="polite">
        {selectedIds.length === 0
          ? `Search and select up to ${maxSelections} ${type} to compare.`
          : selectedIds.length >= maxSelections
            ? `Maximum of ${maxSelections} selections reached.`
            : `${maxSelections - selectedIds.length} more selection${maxSelections - selectedIds.length !== 1 ? "s" : ""} available.`}
        {isNavigating ? " Updating comparison..." : ""}
      </p>
    </div>
  );
}
