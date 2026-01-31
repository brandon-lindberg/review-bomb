"use client";

import { useState, useEffect, useRef } from "react";
import type { Journalist, Outlet } from "@/types";

interface SelectedItem {
  id: number;
  name: string;
  image_url: string | null;
}

interface CompareSelectorProps {
  type: "journalists" | "outlets";
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
              : data.outlets.map((o: Outlet) => ({
                  id: o.id,
                  name: o.name,
                  image_url: o.logo_url,
                  review_count: o.review_count,
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

  const handleSelect = (item: SearchResult) => {
    if (selectedIds.length >= maxSelections) return;

    const newIds = [...selectedIds, item.id];
    const url = new URL(window.location.href);
    url.searchParams.set("ids", newIds.join(","));
    url.searchParams.set("type", type);
    window.location.href = url.toString();
  };

  const handleRemove = (id: number) => {
    const newIds = selectedIds.filter((selectedId) => selectedId !== id);
    const url = new URL(window.location.href);
    if (newIds.length > 0) {
      url.searchParams.set("ids", newIds.join(","));
    } else {
      url.searchParams.delete("ids");
    }
    url.searchParams.set("type", type);
    window.location.href = url.toString();
  };

  return (
    <div className="space-y-4">
      {/* Search Input */}
      {selectedIds.length < maxSelections && (
        <div className="relative" ref={dropdownRef}>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setShowDropdown(true)}
            placeholder={`Search ${type}...`}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
          />

          {/* Dropdown */}
          {showDropdown && (query.length >= 2 || isLoading) && (
            <div className="absolute z-10 w-full mt-1 bg-white rounded-lg shadow-lg border border-gray-200 max-h-60 overflow-y-auto">
              {isLoading ? (
                <div className="px-4 py-3 text-gray-500">Searching...</div>
              ) : results.length > 0 ? (
                results.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleSelect(item)}
                    className="w-full px-4 py-3 text-left hover:bg-gray-50 flex items-center gap-3 transition-colors"
                  >
                    {item.image_url ? (
                      <img
                        src={item.image_url}
                        alt={item.name}
                        className="w-8 h-8 rounded-full object-cover"
                      />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
                        <span className="text-gray-500 text-sm font-medium">
                          {item.name.charAt(0)}
                        </span>
                      </div>
                    )}
                    <div>
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
                <div className="px-4 py-3 text-gray-500">No results found</div>
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
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-blue-100 text-blue-800 rounded-full text-sm"
            >
              {item.image_url ? (
                <img
                  src={item.image_url}
                  alt={item.name}
                  className="w-5 h-5 rounded-full object-cover"
                />
              ) : (
                <span className="w-5 h-5 rounded-full bg-blue-200 flex items-center justify-center text-xs font-medium">
                  {item.name.charAt(0)}
                </span>
              )}
              <span className="font-medium">{item.name}</span>
              <button
                onClick={() => handleRemove(item.id)}
                className="hover:text-blue-600 transition-colors"
                aria-label="Remove"
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
      <p className="text-sm text-gray-500">
        {selectedIds.length === 0
          ? `Search and select up to ${maxSelections} ${type} to compare.`
          : selectedIds.length >= maxSelections
            ? `Maximum of ${maxSelections} selections reached.`
            : `${maxSelections - selectedIds.length} more selection${maxSelections - selectedIds.length !== 1 ? "s" : ""} available.`}
      </p>
    </div>
  );
}
