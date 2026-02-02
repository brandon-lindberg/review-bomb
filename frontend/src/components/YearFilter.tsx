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
      className="pl-4 pr-10 py-2 border border-gray-300 rounded-lg text-sm appearance-none bg-no-repeat"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%235C574F' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
        backgroundPosition: "right 0.75rem center",
        backgroundSize: "1rem",
      }}
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
