import { SEED_CARDS, SEED_SUMMARY } from "@/mocks/seed";
import type { FilterKey, QueryCard, Summary } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function tryFetch<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // backend unreachable → caller uses the seed fallback
  }
}

export async function getFeed(filter: FilterKey, q: string): Promise<{ cards: QueryCard[]; live: boolean }> {
  const params = new URLSearchParams();
  if (filter === "needs_action") params.set("needs_action", "true");
  if (q) params.set("q", q);
  const live = await tryFetch<QueryCard[]>(`/api/reports/feed?${params.toString()}`);
  if (live) return { cards: live, live: true };

  // Seed fallback with client-side filtering so the demo works offline.
  let cards = SEED_CARDS;
  if (filter === "inbound") cards = cards.filter((c) => c.direction === "inbound");
  if (filter === "outbound") cards = cards.filter((c) => c.direction === "outbound");
  if (filter === "needs_action") cards = cards.filter((c) => c.outcome === "callback_needed");
  if (q) {
    const needle = q.toLowerCase();
    cards = cards.filter(
      (c) =>
        (c.customer_name ?? "").toLowerCase().includes(needle) ||
        (c.summary ?? "").toLowerCase().includes(needle) ||
        c.phone_masked.includes(needle),
    );
  }
  return { cards, live: false };
}

export async function getSummary(): Promise<Summary> {
  const live = await tryFetch<Summary>("/api/reports/summary");
  return live ?? SEED_SUMMARY;
}

export async function startOutbound(phone: string, name?: string): Promise<{ ok: boolean }> {
  const res = await tryFetch<unknown>("/api/call_sessions/outbound", {
    method: "POST",
    body: JSON.stringify({ phone, customer_name: name ?? null }),
  });
  return { ok: res !== null };
}
