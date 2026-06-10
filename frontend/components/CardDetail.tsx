"use client";

import { Download, PhoneIncoming, PhoneOutgoing, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  fmtClock,
  fmtDuration,
  fmtExtractedKey,
  fmtExtractedValue,
  outcomeBadgeClass,
} from "@/lib/format";
import { getRecordingUrl } from "@/lib/api";
import { OUTCOME_LABELS, type QueryCard } from "@/lib/types";

export function CardDetail({ card, onClose }: { card: QueryCard | null; onClose: () => void }) {
  const sessionId = card?.call_session_id;
  const [recUrl, setRecUrl] = useState<string | null>(null);
  const [recLoading, setRecLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    setRecLoading(true);
    setRecUrl(null);
    getRecordingUrl(sessionId).then((url) => {
      if (active) {
        setRecUrl(url);
        setRecLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [sessionId]);

  if (!card) return null;

  const Icon = card.direction === "inbound" ? PhoneIncoming : PhoneOutgoing;
  const badgeClass = outcomeBadgeClass(card.outcome);

  return (
    <div className="drawer-scrim" onClick={onClose} role="presentation">
      <aside
        className="drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Call details"
      >
        <header className="dw-head">
          <div>
            <div className="dw-eyebrow">
              <Icon size={14} strokeWidth={2} />
              <span className="capitalize">{card.direction}</span>
              <span>·</span>
              <span>{card.phone_masked}</span>
            </div>
            <h2 className="dw-name">{card.customer_name ?? "Unknown caller"}</h2>
            <div className="dw-meta">
              {fmtClock(card.started_at)} · {fmtDuration(card.duration_s)}
            </div>
          </div>
          <button type="button" className="dw-x" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>

        <div className="dw-body">
          <div>
            <span className={`badge big ${badgeClass}`}>
              <span className="dt" />
              {card.outcome ? OUTCOME_LABELS[card.outcome] : "Pending"}
              {card.confidence != null && (
                <span className="badge-cf">· {Math.round(card.confidence * 100)}%</span>
              )}
            </span>
          </div>

          {card.summary && (
            <section>
              <h3 className="dw-h3">Summary</h3>
              <p className="dw-sum">{card.summary}</p>
            </section>
          )}

          {Object.keys(card.extracted).length > 0 && (
            <section>
              <h3 className="dw-h3">Extracted</h3>
              <div className="dw-ext">
                {Object.entries(card.extracted).map(([k, v]) => (
                  <div key={k} className="ext-cell">
                    <div className="ext-k">{fmtExtractedKey(k)}</div>
                    <div className="ext-v">{fmtExtractedValue(v)}</div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section>
            <h3 className="dw-h3">Recording</h3>
            {recUrl ? (
              <audio controls preload="none" src={recUrl} style={{ width: "100%" }} />
            ) : (
              <p className="dw-sum">
                {recLoading ? "Loading recording…" : "No recording available for this call."}
              </p>
            )}
          </section>

          {card.transcript && card.transcript.length > 0 && (
            <section>
              <h3 className="dw-h3">Transcript</h3>
              <div className="dw-trans">
                {card.transcript.map((t, i) => (
                  <div key={i} className={`tb ${t.role === "agent" ? "agent" : "cust"}`}>
                    <span className="tb-role">{t.role === "agent" ? "Agent" : "Customer"}</span>
                    <div className="tb-bub">{t.text}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        <footer className="dw-foot">
          <button type="button" className="btn-soft">
            <Download size={16} /> Export
          </button>
          <button type="button" className="btn-fill" onClick={onClose}>
            Done
          </button>
        </footer>
      </aside>
    </div>
  );
}
