"use client";

interface ScoreDisplayProps {
  criticScore: number | null | undefined;
  userScore: number | null | undefined;
  label?: string;
  size?: "sm" | "md" | "lg";
}

export function ScoreDisplay({
  criticScore,
  userScore,
  label,
  size = "md",
}: ScoreDisplayProps) {
  const sizeClasses = {
    sm: {
      label: "text-xs",
      score: "text-lg",
      vs: "text-sm",
    },
    md: {
      label: "text-xs",
      score: "text-2xl",
      vs: "text-xl",
    },
    lg: {
      label: "text-sm",
      score: "text-3xl",
      vs: "text-2xl",
    },
  };

  const classes = sizeClasses[size];

  return (
    <div className="flex items-center justify-center sm:justify-start gap-4">
      {label && <span className="text-gray-500 text-sm w-20">{label}</span>}

      <div className="flex items-center gap-2">
        <div className="text-center">
          <div className={`${classes.label} text-gray-500 uppercase`}>
            Critics
          </div>
          <div
            className={`${classes.score} font-bold ${criticScore != null ? "text-purple-600" : "text-gray-300"}`}
          >
            {criticScore != null ? Number(criticScore).toFixed(0) : "—"}
          </div>
        </div>

        <div className={`text-gray-300 ${classes.vs}`}>vs</div>

        <div className="text-center">
          <div className={`${classes.label} text-gray-500 uppercase`}>
            Users
          </div>
          <div
            className={`${classes.score} font-bold ${userScore != null ? "text-blue-600" : "text-gray-300"}`}
          >
            {userScore != null ? Number(userScore).toFixed(0) : "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
