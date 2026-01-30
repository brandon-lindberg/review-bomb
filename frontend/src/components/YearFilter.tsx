"use client";

interface YearFilterProps {
  years: number[];
  defaultValue: number | undefined;
}

export function YearFilter({ years, defaultValue }: YearFilterProps) {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const url = new URL(window.location.href);
    if (e.target.value) {
      url.searchParams.set("year", e.target.value);
    } else {
      url.searchParams.delete("year");
    }
    url.searchParams.delete("page");
    window.location.href = url.toString();
  };

  return (
    <select
      className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
      defaultValue={defaultValue || ""}
      onChange={handleChange}
    >
      <option value="">All Years</option>
      {years.map((y) => (
        <option key={y} value={y}>
          {y}
        </option>
      ))}
    </select>
  );
}
