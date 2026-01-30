"use client";

interface SortOption {
  value: string;
  label: string;
}

interface SortSelectProps {
  options: SortOption[];
  defaultValue: string;
  paramName?: string;
  paramName2?: string;
}

export function SortSelect({
  options,
  defaultValue,
  paramName = "sort",
  paramName2,
}: SortSelectProps) {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const url = new URL(window.location.href);
    const value = e.target.value;

    if (paramName2) {
      // Split value for two params (e.g., "disparity-desc" -> sort=disparity, order=desc)
      const [val1, val2] = value.split("-");
      url.searchParams.set(paramName, val1);
      url.searchParams.set(paramName2, val2);
    } else {
      url.searchParams.set(paramName, value);
    }

    url.searchParams.delete("page");
    window.location.href = url.toString();
  };

  return (
    <select
      className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
      defaultValue={defaultValue}
      onChange={handleChange}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
