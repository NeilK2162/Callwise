"use client";

import { useState } from "react";
import { X, PhoneOutgoing } from "lucide-react";
import { startOutbound } from "@/lib/api";

export function OutboundModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [status, setStatus] = useState<"idle" | "calling" | "done" | "error">("idle");

  if (!open) return null;

  async function trigger() {
    setStatus("calling");
    const { ok } = await startOutbound(phone, name || undefined);
    setStatus(ok ? "done" : "error");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-ink-900/40" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
        <button onClick={onClose} className="absolute right-4 top-4 text-ink-500 hover:text-ink-900">
          <X className="h-5 w-5" />
        </button>
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-50 text-brand-600">
            <PhoneOutgoing className="h-4 w-4" />
          </div>
          <h2 className="text-lg font-semibold text-ink-900">Start Outbound Call</h2>
        </div>

        <label className="mb-1 block text-xs font-medium text-ink-500">Phone number</label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+91 ……"
          className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
        <label className="mb-1 block text-xs font-medium text-ink-500">Name (optional)</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Customer name"
          className="mb-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />

        <button
          onClick={trigger}
          disabled={!phone || status === "calling"}
          className="w-full rounded-lg bg-brand-500 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:opacity-50"
        >
          {status === "calling" ? "Dialing…" : "Call now"}
        </button>

        {status === "done" && (
          <p className="mt-3 text-center text-sm text-emerald-600">
            Call queued — the outcome will appear in the feed.
          </p>
        )}
        {status === "error" && (
          <p className="mt-3 text-center text-sm text-amber-600">
            Backend not connected — this is a demo trigger.
          </p>
        )}
      </div>
    </div>
  );
}
