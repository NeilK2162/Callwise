import { fmtDuration } from "@/lib/format";
import type { Summary } from "@/lib/types";

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${accent ?? "text-ink-900"}`}>{value}</div>
      {sub && <div className="text-xs text-ink-500">{sub}</div>}
    </div>
  );
}

export function StatsBar({ summary }: { summary: Summary }) {
  const bookedPct = summary.calls_today
    ? Math.round((summary.booked / summary.calls_today) * 100)
    : 0;
  return (
    <div className="flex flex-wrap gap-3">
      <Stat label="Calls" value={String(summary.calls_today)} sub="today" />
      <Stat label="Booked" value={String(summary.booked)} sub={`${bookedPct}%`} accent="text-emerald-600" />
      <Stat label="Callback" value={String(summary.callback_needed)} sub="needs action" accent="text-amber-600" />
      <Stat label="Missed" value={String(summary.missed)} sub="never!" accent="text-emerald-600" />
      <Stat label="Avg length" value={fmtDuration(Math.round(summary.avg_duration_s))} />
    </div>
  );
}
