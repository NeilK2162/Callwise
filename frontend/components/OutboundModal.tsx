"use client";

import { useState } from "react";
import { Check, PhoneOutgoing, X } from "lucide-react";
import { startOutbound } from "@/lib/api";

type Phase = "idle" | "calling" | "done" | "error";

export function OutboundModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");

  if (!open) return null;

  function resetAndClose() {
    setPhase("idle");
    setPhone("");
    setName("");
    onClose();
  }

  async function trigger() {
    setPhase("calling");
    const { ok } = await startOutbound(phone, name || undefined);
    setPhase(ok ? "done" : "error");
  }

  return (
    <div className="modal-scrim" onClick={resetAndClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <button type="button" className="modal-x" onClick={resetAndClose} aria-label="Close">
          <X size={18} />
        </button>

        {phase === "idle" && (
          <>
            <div className="ob-icon">
              <PhoneOutgoing size={22} strokeWidth={2} />
            </div>
            <h2 className="ob-title">Start outbound call</h2>
            <p className="ob-desc">
              Enter a number and Callwise will dial through the same governed path as campaign
              calls — outcome lands in the feed automatically.
            </p>
            <label className="ob-label" htmlFor="ob-phone">
              Phone number
            </label>
            <input
              id="ob-phone"
              className="ob-input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 …"
            />
            <label className="ob-label" htmlFor="ob-name">
              Name <span className="ob-opt">(optional)</span>
            </label>
            <input
              id="ob-name"
              className="ob-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Customer name"
            />
            <button
              type="button"
              className="btn-fill ob-go"
              onClick={trigger}
              disabled={!phone.trim()}
            >
              Call now
            </button>
          </>
        )}

        {phase === "calling" && (
          <div className="ob-done">
            <p className="ob-status" style={{ justifyContent: "center", display: "flex", gap: 8 }}>
              <span className="ob-ring" /> Dialing…
            </p>
            <p className="ob-num">{phone}</p>
          </div>
        )}

        {phase === "done" && (
          <div className="ob-done">
            <div className="ob-check">
              <Check size={28} strokeWidth={2.5} />
            </div>
            <h2 className="ob-title">Call queued</h2>
            <p className="ob-desc">The outcome will appear in your feed in a few seconds.</p>
            <span className="badge badge-booked">
              <span className="dt" /> Queued for dial
            </span>
            <button type="button" className="btn-fill ob-go" onClick={resetAndClose}>
              Back to feed
            </button>
          </div>
        )}

        {phase === "error" && (
          <div className="ob-done">
            <h2 className="ob-title">Could not queue call</h2>
            <p className="ob-desc">
              Backend not connected — start the API stack or use demo seed data offline.
            </p>
            <p className="ob-err">Check docker compose / NEXT_PUBLIC_API_BASE_URL</p>
            <button type="button" className="btn-soft ob-go" onClick={() => setPhase("idle")}>
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
