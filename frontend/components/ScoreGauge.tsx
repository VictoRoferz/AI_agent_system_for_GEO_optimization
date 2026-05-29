"use client";

function color(score: number): string {
  if (score >= 70) return "#0f9b8e";
  if (score >= 40) return "#ca8a04";
  return "#b91c1c";
}

export default function ScoreGauge({
  score,
  size = 120,
  label,
}: {
  score: number;
  size?: number;
  label?: string;
}) {
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r;
  const dash = (score / 100) * c;
  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={10} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color(score)}
            strokeWidth={10}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${c}`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-2xl font-bold text-navy-900">{score}</div>
          <div className="text-[10px] uppercase tracking-wide text-slate-400">/ 100</div>
        </div>
      </div>
      {label && <div className="mt-1 text-sm font-medium text-slate-600">{label}</div>}
    </div>
  );
}
