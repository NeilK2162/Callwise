"use client";

import { useEffect, useState } from "react";
import { PhoneOutgoing } from "lucide-react";
import { StatsBar } from "@/components/StatsBar";
import { Filters } from "@/components/Filters";
import { QueryCard } from "@/components/QueryCard";
import { CardDetail } from "@/components/CardDetail";
import { OutboundModal } from "@/components/OutboundModal";
import { getFeed, getSummary } from "@/lib/api";
import { SEED_SUMMARY } from "@/mocks/seed";
import type { FilterKey, QueryCard as Card, Summary } from "@/lib/types";

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary>(SEED_SUMMARY);
  const [cards, setCards] = useState<Card[]>([]);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Card | null>(null);
  const [outboundOpen, setOutboundOpen] = useState(false);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSummary().then(setSummary);
  }, []);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      getFeed(filter, query).then(({ cards, live }) => {
        setCards(cards);
        setLive(live);
        setLoading(false);
      });
    }, 200);
    return () => clearTimeout(handle);
  }, [filter, query]);

  return (
    <div className="mx-auto min-h-screen max-w-5xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold tracking-tight text-brand-600">Callwise</span>
          <span className="text-sm text-ink-500">Clinic Dashboard</span>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
              live ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-ink-500"
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-500" : "bg-slate-400"}`} />
            {live ? "Live" : "Demo data"}
          </span>
        </div>
        <button
          onClick={() => setOutboundOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-500 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-600"
        >
          <PhoneOutgoing className="h-4 w-4" /> Start Outbound Call
        </button>
      </header>

      <div className="mb-5">
        <StatsBar summary={summary} />
      </div>

      <div className="mb-4">
        <Filters active={filter} onChange={setFilter} query={query} onQuery={setQuery} />
      </div>

      <div className="space-y-3">
        {loading && cards.length === 0 && (
          <div className="py-12 text-center text-sm text-ink-500">Loading feed…</div>
        )}
        {!loading && cards.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 py-12 text-center text-sm text-ink-500">
            No calls match this view yet.
          </div>
        )}
        {cards.map((card) => (
          <QueryCard key={card.call_session_id} card={card} onOpen={setSelected} />
        ))}
      </div>

      <CardDetail card={selected} onClose={() => setSelected(null)} />
      <OutboundModal open={outboundOpen} onClose={() => setOutboundOpen(false)} />
    </div>
  );
}
