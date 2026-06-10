import type { Outcome } from "@/lib/types";

export function fmtDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function fmtRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

const DISPLAY_LOCALE = "en-US";

export function fmtClock(iso: string): string {
  return new Date(iso).toLocaleString(DISPLAY_LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  });
}

/** Humanize an extracted-field key: "booked_for" → "Booked for". */
export function fmtExtractedKey(key: string): string {
  const s = key.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** Render an extracted value; ISO timestamps (e.g. booked_for) become a readable local date. */
export function fmtExtractedValue(value: unknown): string {
  if (typeof value === "string" && ISO_DATETIME.test(value)) {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleString(DISPLAY_LOCALE, {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    }
  }
  return String(value);
}

const OUTCOME_STYLES: Record<Outcome, { badge: string; emoji: string }> = {
  appointment_booked: { badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", emoji: "✅" },
  question_answered: { badge: "bg-sky-50 text-sky-700 ring-sky-600/20", emoji: "💬" },
  callback_needed: { badge: "bg-amber-50 text-amber-700 ring-amber-600/20", emoji: "↩️" },
  not_interested: { badge: "bg-slate-100 text-slate-600 ring-slate-500/20", emoji: "🚫" },
  wrong_number: { badge: "bg-slate-100 text-slate-600 ring-slate-500/20", emoji: "❓" },
  wrong_party: { badge: "bg-slate-100 text-slate-600 ring-slate-500/20", emoji: "❓" },
  voicemail: { badge: "bg-violet-50 text-violet-700 ring-violet-600/20", emoji: "📩" },
  opt_out: { badge: "bg-rose-50 text-rose-700 ring-rose-600/20", emoji: "⛔" },
  undetermined: { badge: "bg-slate-100 text-slate-500 ring-slate-500/20", emoji: "•" },
};

export function outcomeStyle(o: Outcome | null) {
  return o ? OUTCOME_STYLES[o] : { badge: "bg-slate-100 text-slate-500 ring-slate-500/20", emoji: "•" };
}

/** CSS badge variant class from the integrated dashboard design. */
export function outcomeBadgeClass(o: Outcome | null): string {
  switch (o) {
    case "appointment_booked":
      return "badge-booked";
    case "callback_needed":
      return "badge-callback";
    case "question_answered":
      return "badge-answered";
    case "voicemail":
      return "badge-voicemail";
    case "opt_out":
      return "badge-optout";
    default:
      return "badge-muted";
  }
}
