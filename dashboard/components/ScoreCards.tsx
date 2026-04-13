"use client";

interface Props {
  lighthouse: Record<string, number>;
}

const CATEGORIES = [
  { key: "performance", label: "Performance", color: "blue" },
  { key: "accessibility", label: "Accessibility", color: "green" },
  { key: "best_practices", label: "Best Practices", color: "purple" },
  { key: "seo", label: "SEO", color: "orange" },
];

function getScoreColor(score: number): string {
  if (score >= 90) return "text-green-400";
  if (score >= 50) return "text-orange-400";
  return "text-red-400";
}

function getBarColor(score: number): string {
  if (score >= 90) return "bg-green-500";
  if (score >= 50) return "bg-orange-500";
  return "bg-red-500";
}

export default function ScoreCards({ lighthouse }: Props) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {CATEGORIES.map(({ key, label }) => {
        const score = lighthouse[key] ?? 0;
        return (
          <div
            key={key}
            className="rounded-xl border border-gray-800 bg-[#141414] p-5"
          >
            <p className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
              {label}
            </p>
            <p className={`text-3xl font-bold ${getScoreColor(score)}`}>
              {score}
            </p>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-800">
              <div
                className={`h-full rounded-full transition-all duration-700 ${getBarColor(score)}`}
                style={{ width: `${score}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
