import { fmtDuration } from "@/lib/format";
import type { Summary } from "@/lib/types";

function sparkBars(seed: number, color: string) {
  return Array.from({ length: 12 }, (_, i) => {
    const h = 4 + Math.abs(Math.sin(i * 0.55 + seed)) * 18;
    return (
      <i
        key={i}
        style={{
          height: `${h.toFixed(0)}px`,
          background: color,
        }}
      />
    );
  });
}

function Stat({
  label,
  value,
  sub,
  color,
  seed,
}: {
  label: string;
  value: string;
  sub?: string;
  color: string;
  seed: number;
}) {
  return (
    <div className="stat">
      <div className="stat-k">{label}</div>
      <div className="stat-v" style={{ color: color === "inherit" ? undefined : color }}>
        {value}
      </div>
      {sub && <div className="stat-sub">{sub}</div>}
      <div className="stat-spark">{sparkBars(seed, color === "inherit" ? "var(--brand)" : color)}</div>
    </div>
  );
}

export function StatsBar({ summary }: { summary: Summary }) {
  const bookedPct = summary.calls_today
    ? Math.round((summary.booked / summary.calls_today) * 100)
    : 0;

  return (
    <div className="stats">
      <Stat label="Calls" value={String(summary.calls_today)} sub="today" color="inherit" seed={0} />
      <Stat
        label="Booked"
        value={String(summary.booked)}
        sub={`${bookedPct}%`}
        color="var(--emerald)"
        seed={1}
      />
      <Stat
        label="Callback"
        value={String(summary.callback_needed)}
        sub="needs action"
        color="var(--amber)"
        seed={2}
      />
      <Stat
        label="Missed"
        value={String(summary.missed)}
        sub="never!"
        color="var(--emerald)"
        seed={3}
      />
      <Stat
        label="Avg length"
        value={fmtDuration(Math.round(summary.avg_duration_s))}
        color="var(--sky)"
        seed={4}
      />
    </div>
  );
}
