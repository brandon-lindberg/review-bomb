"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

interface SiteSelectOption {
  value: string;
  label: string;
}

interface SiteSelectProps {
  options: SiteSelectOption[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
  disabled?: boolean;
  pending?: boolean;
}

export function SiteSelect({
  options,
  value,
  onChange,
  className,
  disabled = false,
  pending = false,
}: SiteSelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listboxId = useId();
  const isOpen = open && !disabled;

  const selectedOption = useMemo(
    () => options.find((option) => option.value === value) ?? options[0],
    [options, value]
  );

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleSelect = (nextValue: string) => {
    setOpen(false);
    if (nextValue !== value) {
      onChange(nextValue);
    }
  };

  return (
    <div ref={containerRef} className={`relative${className ? ` ${className}` : ""}`}>
      <button
        ref={buttonRef}
        type="button"
        className="site-field relative w-full py-3 text-sm disabled:opacity-80"
        onClick={() => {
          if (!disabled) setOpen((current) => !current);
        }}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
      >
        <span className="grid w-full grid-cols-[2.75rem_minmax(0,1fr)_2.75rem] items-center">
          <span aria-hidden="true" />
          <span className="truncate text-center">
            {selectedOption?.label ?? ""}
          </span>
          <span
            className="flex items-center justify-center"
            aria-hidden="true"
          >
            {pending ? (
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-t-transparent"
                style={{ borderColor: "var(--foreground-muted)", borderTopColor: "transparent" }}
              />
            ) : (
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
                style={{ color: "var(--foreground-muted)" }}
              >
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            )}
          </span>
        </span>
      </button>

      {isOpen && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-40 mt-2 overflow-hidden rounded-[1.15rem] border shadow-lg"
          style={{
            borderColor: "var(--border-strong)",
            background:
              "linear-gradient(180deg, var(--background-card-strong), var(--background-card))",
            boxShadow: "var(--shadow-strong)",
          }}
        >
          <div className="max-h-80 overflow-y-auto p-1.5">
            {options.map((option) => {
              const isSelected = option.value === value;

              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className="flex w-full items-center rounded-[0.95rem] px-4 py-3 text-left text-sm font-medium"
                  style={
                    isSelected
                      ? {
                          backgroundColor:
                            "color-mix(in srgb, var(--background-card-strong) 82%, var(--color-rust) 18%)",
                          color: "var(--foreground)",
                        }
                      : {
                          color: "var(--foreground)",
                        }
                  }
                  onClick={() => handleSelect(option.value)}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
