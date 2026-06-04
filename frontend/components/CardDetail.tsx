"use client";

import { X, Play, Download, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import { fmtClock, fmtDuration, outcomeStyle } from "@/lib/format";
import { OUTCOME_LABELS, type QueryCard } from "@/lib/types";

export function CardDetail({ card, onClose }: { card: QueryCard | null; onClose: () => void }) {
  if (!card) return null;
  const style = outcomeStyle(card.outcome);
  const Icon = card.direction === "inbound" ? PhoneIncoming : PhoneOutgoing;

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-ink-900/30" onClick={onClose} />
      <aside className="animate-slide-in absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
        <header className="flex items-start justify-between border-b border-slate-200 p-5">
          <div>
            <div className="flex items-center gap-2 text-xs text-ink-500">
              <Icon className="h-3.5 w-3.5" />
              <span className="font-medium uppercase tracking-wide">{card.direction}</span>
              <span>·</span>
              <span>{card.phone_masked}</span>
            </div>
            <h2 className="mt-1 text-lg font-semibold text-ink-900">
              {card.customer_name ?? "Unknown caller"}
            </h2>
            <div className="text-xs text-ink-500">
              {fmtClock(card.started_at)} · {fmtDuration(card.duration_s)}
            </div>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-ink-500 hover:bg-slate-100">
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          <div>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm font-medium ring-1 ring-inset ${style.badge}`}
            >
              <span>{style.emoji}</span>
              {card.outcome ? OUTCOME_LABELS[card.outcome] : "Pending"}
              {card.confidence != null && (
                <span className="ml-1 opacity-70">· {Math.round(card.confidence * 100)}%</span>
              )}
            </span>
          </div>

          {card.summary && (
            <section>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">
                Summary
              </h3>
              <p className="text-sm text-ink-700">{card.summary}</p>
            </section>
          )}

          {Object.keys(card.extracted).length > 0 && (
            <section>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">
                Extracted
              </h3>
              <dl className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(card.extracted).map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-slate-50 px-3 py-2">
                    <dt className="text-[11px] uppercase text-ink-500">{k}</dt>
                    <dd className="text-ink-900">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
              Recording
            </h3>
            <div className="flex items-center gap-3 rounded-lg border border-slate-200 p-3">
              <button className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500 text-white">
                <Play className="h-4 w-4" />
              </button>
              <div className="h-1.5 flex-1 rounded-full bg-slate-200">
                <div className="h-1.5 w-1/3 rounded-full bg-brand-500" />
              </div>
              <span className="text-xs text-ink-500">{fmtDuration(card.duration_s)}</span>
            </div>
          </section>

          {card.transcript && card.transcript.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                Transcript
              </h3>
              <div className="space-y-2">
                {card.transcript.map((t, i) => (
                  <div
                    key={i}
                    className={t.role === "agent" ? "text-left" : "text-right"}
                  >
                    <div
                      className={`inline-block max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                        t.role === "agent"
                          ? "bg-slate-100 text-ink-900"
                          : "bg-brand-500 text-white"
                      }`}
                    >
                      {t.text}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        <footer className="border-t border-slate-200 p-4">
          <button className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 py-2 text-sm font-medium text-ink-700 hover:bg-slate-50">
            <Download className="h-4 w-4" /> Export
          </button>
        </footer>
      </aside>
    </div>
  );
}
