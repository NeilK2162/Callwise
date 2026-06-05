"use client";

import { ChevronRight, FileText, PhoneIncoming, PhoneOutgoing, Play } from "lucide-react";
import { fmtClock, fmtDuration, outcomeBadgeClass } from "@/lib/format";
import { OUTCOME_LABELS, type QueryCard as Card } from "@/lib/types";

export function QueryCard({
  card,
  onOpen,
  isNew,
}: {
  card: Card;
  onOpen: (c: Card) => void;
  isNew?: boolean;
}) {
  const Icon = card.direction === "inbound" ? PhoneIncoming : PhoneOutgoing;
  const extractedPairs = Object.entries(card.extracted).slice(0, 4);
  const badgeClass = outcomeBadgeClass(card.outcome);

  return (
    <button
      type="button"
      onClick={() => onOpen(card)}
      className={`qcard${isNew ? " qcard-new" : ""}`}
    >
      <span className="qc-rail" aria-hidden />
      <div className="qc-main">
        <div className="qc-top">
          <span className={`qc-dir ${card.direction === "inbound" ? "in" : "out"}`}>
            <Icon size={14} strokeWidth={2.2} />
            {card.direction === "inbound" ? "Inbound" : "Outbound"}
          </span>
          <span className="qc-dot">·</span>
          <span>{card.phone_masked}</span>
          <span className="qc-dot">·</span>
          <span>{fmtClock(card.started_at)}</span>
          {card.duration_s != null && (
            <>
              <span className="qc-dot">·</span>
              <span>{fmtDuration(card.duration_s)}</span>
            </>
          )}
        </div>
        <div className="qc-name-row">
          <span className="qc-name">{card.customer_name ?? "Unknown caller"}</span>
          <span className={`badge ${badgeClass}`}>
            <span className="dt" />
            {card.outcome ? OUTCOME_LABELS[card.outcome] : "Pending"}
          </span>
        </div>
        {card.summary && <p className="qc-sum">{card.summary}</p>}
        {extractedPairs.length > 0 && (
          <div className="qc-tags">
            {extractedPairs.map(([k, v]) => (
              <span key={k} className="tag">
                <b>{k}</b>={String(v)}
              </span>
            ))}
          </div>
        )}
        <div className="qc-foot">
          {card.has_recording && (
            <span className="qc-meta">
              <Play size={13} strokeWidth={2} /> Recording
            </span>
          )}
          <span className="qc-meta">
            <FileText size={13} strokeWidth={2} /> Transcript
          </span>
          {card.confidence != null && (
            <span className="qc-conf">confidence {Math.round(card.confidence * 100)}%</span>
          )}
        </div>
      </div>
      <span className="qc-go" aria-hidden>
        <ChevronRight size={18} />
      </span>
    </button>
  );
}
