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
      className="pl-4 pr-10 py-2 border border-gray-300 rounded-lg text-sm appearance-none bg-no-repeat"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%235C574F' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
        backgroundPosition: "right 0.75rem center",
        backgroundSize: "1rem",
      }}
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
