"use client";

interface ScoreDisplayProps {
  criticScore: number | null | undefined;
  userScore?: number | null | undefined;
  steamUserScore?: number | null | undefined;
  metacriticUserScore?: number | null | undefined;
  label?: string;
  size?: "sm" | "md" | "lg";
}

export function ScoreDisplay({
  criticScore,
  userScore,
  steamUserScore,
  metacriticUserScore,
  label,
  size = "md",
}: ScoreDisplayProps) {
  const sizeClasses = {
    sm: {
      label: "text-[10px]",
      score: "text-lg",
      gap: "gap-3",
      sectionMinWidth: "min-w-[52px]",
    },
    md: {
      label: "text-xs",
      score: "text-2xl",
      gap: "gap-4",
      sectionMinWidth: "min-w-[72px]",
    },
    lg: {
      label: "text-sm",
      score: "text-3xl",
      gap: "gap-5",
      sectionMinWidth: "min-w-[92px]",
    },
  };

  const classes = sizeClasses[size];
  const fallbackUserScore = userScore ?? null;
  const scoreSections = [
    {
      key: "critics",
      label: "Critics",
      value: criticScore,
      colorClass: "text-purple-600",
    },
    {
      key: "steam",
      label: "Steam",
      value: steamUserScore,
      colorClass: "text-blue-600",
    },
    {
      key: "metacritic",
      label: "Metacritic",
      value: metacriticUserScore,
      colorClass: "text-orange-500",
    },
  ].filter((section) => {
    if (section.key === "critics") {
      return true;
    }

    if (section.value != null) {
      return true;
    }

    // Backward-compatible path for callers that only pass userScore.
    return section.key === "steam" && fallbackUserScore != null;
  });

  return (
    <div className="flex items-center justify-center sm:justify-start gap-4">
      {label && <span className="text-gray-500 text-sm w-20">{label}</span>}

      <div className={`flex items-center ${classes.gap}`}>
        {scoreSections.map((section) => {
          const value =
            section.value != null
              ? section.value
              : section.key === "steam" && fallbackUserScore != null
                ? fallbackUserScore
                : null;

          return (
            <div key={section.key} className={`text-center ${classes.sectionMinWidth}`}>
              <div className={`${classes.label} text-gray-500 uppercase`}>
                {section.label}
              </div>
              <div
                className={`${classes.score} font-bold ${value != null ? section.colorClass : "text-gray-300"}`}
              >
                {value != null ? Number(value).toFixed(0) : "—"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
