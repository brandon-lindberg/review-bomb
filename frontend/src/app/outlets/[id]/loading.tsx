export default function OutletDetailLoading() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div
          className="h-10 w-10 animate-spin rounded-full border-4 border-solid border-t-transparent"
          style={{
            borderColor: "var(--border)",
            borderTopColor: "transparent",
          }}
          aria-label="Loading outlet details"
        />
        <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
          Loading outlet details...
        </p>
      </div>
    </div>
  );
}
