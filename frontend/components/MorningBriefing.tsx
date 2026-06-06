"use client";

import { apptValue, fmtMoney } from "@/lib/money";
import { useCountUp } from "@/lib/useCountUp";
import type { Summary } from "@/lib/types";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

/** The hero of the dashboard: one human sentence + the money number. Reframes "a feed of
 * calls" into "the night took care of itself, and here's what it made you." (PRD §0.3) */
export function MorningBriefing({ summary }: { summary: Summary }) {
  const money = useCountUp(summary.booked * apptValue());
  const calls = useCountUp(summary.calls_today, 700);

  return (
    <section className="brief">
      <div className="brief-main">
        <p className="brief-eyebrow eyebrow">{greeting()}</p>
        <p className="brief-line serif">
          While you were away, Callwise answered{" "}
          <b>{Math.round(calls)} {summary.calls_today === 1 ? "call" : "calls"}</b> and booked{" "}
          <b>{summary.booked} {summary.booked === 1 ? "appointment" : "appointments"}</b>.
        </p>
        <p className="brief-money">
          {fmtMoney(money)} <span>in booked value</span>
        </p>
      </div>
      <div className="brief-zero" title="Calls go to voicemail no more.">
        <b>{summary.missed}</b>
        <span>
          missed
          <br />
          24/7 · always on
        </span>
      </div>
    </section>
  );
}
