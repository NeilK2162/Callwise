"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PhoneOutgoing, Search } from "lucide-react";
import { SidebarRail } from "@/components/dashboard/SidebarRail";
import { MorningBriefing } from "@/components/MorningBriefing";
import { StatsBar } from "@/components/StatsBar";
import { Filters } from "@/components/Filters";
import { QueryCard } from "@/components/QueryCard";
import { CardDetail } from "@/components/CardDetail";
import { OutboundModal } from "@/components/OutboundModal";
import { connectFeedSocket, getFeed, getSummary, isDemo } from "@/lib/api";
import type { FilterKey, QueryCard as Card, Summary } from "@/lib/types";

const EMPTY_SUMMARY: Summary = {
  calls_today: 0,
  booked: 0,
  callback_needed: 0,
  missed: 0,
  avg_duration_s: 0,
};

const AGENT_NUMBER = process.env.NEXT_PUBLIC_AGENT_NUMBER ?? "+1 385 396 2012";

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY);
  const [cards, setCards] = useState<Card[]>([]);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Card | null>(null);
  const [outboundOpen, setOutboundOpen] = useState(false);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const [demo, setDemo] = useState(false);
  const [newCardId, setNewCardId] = useState<string | null>(null);
  const prevTopId = useRef<string | null>(null);

  useEffect(() => setDemo(isDemo()), []);

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
  const chip = demo ? "Demo" : live ? "Live" : "Offline";
  const isPristine = filter === "all" && !query;

  return (
    <div className="shell">
      <SidebarRail />

      <div className="main">
        <div className="main-in">
          <header className="top">
            <div className="top-l">
              <h1 className="top-title">Clinic Dashboard</h1>
              <span className={`livechip${live || demo ? " on" : ""}`}>
                <span className="lc-dot" />
                {chip}
              </span>
            </div>
            <div className="top-r">
              <label className="search">
                <Search size={16} strokeWidth={2} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search name, summary, number…"
                  autoComplete="off"
                  data-1p-ignore
                  data-lpignore="true"
                  suppressHydrationWarning
                />
              </label>
              <button
                type="button"
                className="btn-fill"
                onClick={() => setOutboundOpen(true)}
                suppressHydrationWarning
              >
                <PhoneOutgoing size={16} strokeWidth={2} />
                Start Outbound Call
              </button>
            </div>
          </header>

          <MorningBriefing summary={summary} />

          <StatsBar summary={summary} />

          <Filters
            active={filter}
            onChange={setFilter}
            needsActionCount={needsActionCount}
            resultCount={cards.length}
          />

          <div className="feed">
            {loading && cards.length === 0 && <div className="empty">Loading feed…</div>}

            {!loading && cards.length === 0 && isPristine && (
              <div className="onair">
                <div className="onair-mark">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <h3 className="onair-h serif">Your receptionist is on air</h3>
                <p className="onair-p">
                  Call your Callwise number and your first query card lands here in seconds —
                  answered, booked, tagged, and transcribed.
                </p>
                <a className="btn-fill" href={`tel:${AGENT_NUMBER.replace(/[^+\d]/g, "")}`}>
                  <PhoneOutgoing size={16} strokeWidth={2} /> Call the agent
                </a>
                <p className="onair-num mono">{AGENT_NUMBER}</p>
              </div>
            )}

            {!loading && cards.length === 0 && !isPristine && (
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
