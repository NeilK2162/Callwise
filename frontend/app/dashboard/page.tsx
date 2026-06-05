"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PhoneOutgoing, Search } from "lucide-react";
import { SidebarRail } from "@/components/dashboard/SidebarRail";
import { StatsBar } from "@/components/StatsBar";
import { Filters } from "@/components/Filters";
import { QueryCard } from "@/components/QueryCard";
import { CardDetail } from "@/components/CardDetail";
import { OutboundModal } from "@/components/OutboundModal";
import { connectFeedSocket, getFeed, getSummary } from "@/lib/api";
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
  const [tick, setTick] = useState(0);
  const [newCardId, setNewCardId] = useState<string | null>(null);
  const prevTopId = useRef<string | null>(null);

  useEffect(() => {
    getSummary().then(setSummary);
  }, [tick]);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      getFeed(filter, query).then(({ cards: next, live: isLive }) => {
        if (next[0]?.call_session_id && prevTopId.current && next[0].call_session_id !== prevTopId.current) {
          setNewCardId(next[0].call_session_id);
          window.setTimeout(() => setNewCardId(null), 1500);
        }
        prevTopId.current = next[0]?.call_session_id ?? null;
        setCards(next);
        setLive(isLive);
        setLoading(false);
      });
    }, 200);
    return () => clearTimeout(handle);
  }, [filter, query, tick]);

  useEffect(() => {
    const disconnect = connectFeedSocket(() => setTick((t) => t + 1));
    return disconnect;
  }, []);

  const needsActionCount = cards.filter((c) => c.outcome === "callback_needed").length;

  return (
    <div className="shell">
      <SidebarRail />

      <div className="main">
        <div className="main-in">
          <header className="top">
            <div className="top-l">
              <h1 className="top-title">Clinic Dashboard</h1>
              <span className={`livechip${live ? " on" : ""}`}>
                <span className="lc-dot" />
                {live ? "Live" : "Demo data"}
              </span>
            </div>
            <div className="top-r">
              <label className="search">
                <Search size={16} strokeWidth={2} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search name, summary, number…"
                />
              </label>
              <button type="button" className="btn-fill" onClick={() => setOutboundOpen(true)}>
                <PhoneOutgoing size={16} strokeWidth={2} />
                Start Outbound Call
              </button>
            </div>
          </header>

          <StatsBar summary={summary} />

          <Filters
            active={filter}
            onChange={setFilter}
            needsActionCount={needsActionCount}
            resultCount={cards.length}
          />

          <div className="feed">
            {loading && cards.length === 0 && (
              <div className="empty">Loading feed…</div>
            )}
            {!loading && cards.length === 0 && (
              <div className="empty">No calls match this view yet.</div>
            )}
            {cards.map((card) => (
              <QueryCard
                key={card.call_session_id}
                card={card}
                onOpen={setSelected}
                isNew={card.call_session_id === newCardId}
              />
            ))}
          </div>

          <p className="main-foot">
            <Link href="/">← Back to landing</Link>
          </p>
        </div>
      </div>

      <CardDetail card={selected} onClose={() => setSelected(null)} />
      <OutboundModal open={outboundOpen} onClose={() => setOutboundOpen(false)} />
    </div>
  );
}
