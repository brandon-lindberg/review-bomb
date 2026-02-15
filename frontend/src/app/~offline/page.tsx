"use client";

export default function OfflinePage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <h1 className="text-3xl font-bold mb-4" style={{ color: "var(--color-rust)" }}>
        You're Offline
      </h1>
      <p className="text-lg mb-6" style={{ color: "var(--foreground-muted)" }}>
        It looks like you've lost your internet connection. Please check your
        connection and try again.
      </p>
      <button
        onClick={() => window.location.reload()}
        className="px-6 py-3 rounded-lg text-white font-medium transition-opacity hover:opacity-90"
        style={{ backgroundColor: "var(--color-rust)" }}
      >
        Try Again
      </button>
    </div>
  );
}
