"use client";

import { PhoneIncoming, PhoneOutgoing, Play, FileText } from "lucide-react";
import { fmtClock, fmtDuration, outcomeStyle } from "@/lib/format";
import { OUTCOME_LABELS, type QueryCard as Card } from "@/lib/types";

export function QueryCard({ card, onOpen }: { card: Card; onOpen: (c: Card) => void }) {
  const style = outcomeStyle(card.outcome);
  const Icon = card.direction === "inbound" ? PhoneIncoming : PhoneOutgoing;
  const extractedPairs = Object.entries(card.extracted).slice(0, 4);

  return (
    <button
      onClick={() => onOpen(card)}
      className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-brand-500 hover:shadow-md"
    >
      <div className="flex items-center gap-2 text-xs text-ink-500">
        <Icon className="h-3.5 w-3.5" />
        <span className="font-medium uppercase tracking-wide">{card.direction}</span>
        <span>·</span>
        <span>{card.phone_masked}</span>
        <span>·</span>
        <span>{fmtClock(card.started_at)}</span>
        {card.duration_s != null && (
          <>
            <span>·</span>
            <span>{fmtDuration(card.duration_s)}</span>
          </>
        )}
      </div>

      <div className="mt-2 flex items-baseline justify-between gap-3">
        <div className="font-semibold text-ink-900">{card.customer_name ?? "Unknown caller"}</div>
        <span
          className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${style.badge}`}
        >
          <span>{style.emoji}</span>
          {card.outcome ? OUTCOME_LABELS[card.outcome] : "Pending"}
        </span>
      </div>

      {card.summary && <p className="mt-1 line-clamp-2 text-sm text-ink-700">{card.summary}</p>}

      {extractedPairs.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {extractedPairs.map(([k, v]) => (
            <span key={k} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-ink-500">
              {k}={String(v)}
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center gap-4 text-xs font-medium text-ink-500">
        {card.has_recording && (
          <span className="inline-flex items-center gap-1">
            <Play className="h-3.5 w-3.5" /> Recording
          </span>
        )}
        <span className="inline-flex items-center gap-1">
          <FileText className="h-3.5 w-3.5" /> Transcript
        </span>
        {card.confidence != null && (
          <span className="ml-auto">confidence {Math.round(card.confidence * 100)}%</span>
        )}
      </div>
    </button>
  );
}
