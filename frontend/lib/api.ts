import { DEMO_CARDS, DEMO_SUMMARY } from "@/lib/demo";
import type { FilterKey, QueryCard, Summary } from "@/lib/types";

const EMPTY_SUMMARY: Summary = {
  calls_today: 0,
  booked: 0,
  callback_needed: 0,
  missed: 0,
  avg_duration_s: 0,
};

/** Opt-in demo mode: /dashboard?demo=1 renders curated sample data for screen-records. */
export function isDemo(): boolean {
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).get("demo") === "1";
}

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
// Demo auto-login keeps the dashboard friction-free (PRD §0.7: no login screen) while
// the backend stays properly authenticated + row-scoped.
const DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_EMAIL ?? "demo@callwise.dev";
const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD ?? "demo12345";

let _token: string | null = null;
let _tokenPromise: Promise<string | null> | null = null;

async function login(): Promise<string | null> {
  try {
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    _token = (await res.json()).access_token as string;
    return _token;
  } catch {
    return null;
  }
}

export async function ensureToken(): Promise<string | null> {
  if (_token) return _token;
  if (!_tokenPromise) _tokenPromise = login().finally(() => (_tokenPromise = null));
  return _tokenPromise;
}

async function authedFetch<T>(path: string, init?: RequestInit): Promise<T | null> {
  const token = await ensureToken();
  if (!token) return null;
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (res.status === 401) {
      _token = null;
      return null;
    }
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // backend unreachable → caller uses the seed fallback
  }
}

export async function getFeed(
  filter: FilterKey,
  q: string,
): Promise<{ cards: QueryCard[]; live: boolean }> {
  if (isDemo()) return { cards: filterCards(DEMO_CARDS, filter, q), live: false };

  const params = new URLSearchParams();
  if (filter === "needs_action") params.set("needs_action", "true");
  if (q) params.set("q", q);
  const live = await authedFetch<QueryCard[]>(`/api/reports/feed?${params.toString()}`);
  if (!live) return { cards: [], live: false }; // backend down → real empty state, no mock data
  let cards = live;
  if (filter === "inbound") cards = cards.filter((c) => c.direction === "inbound");
  if (filter === "outbound") cards = cards.filter((c) => c.direction === "outbound");
  return { cards, live: true };
}

function filterCards(all: QueryCard[], filter: FilterKey, q: string): QueryCard[] {
  let cards = all;
  if (filter === "inbound") cards = cards.filter((c) => c.direction === "inbound");
  if (filter === "outbound") cards = cards.filter((c) => c.direction === "outbound");
  if (filter === "needs_action") cards = cards.filter((c) => c.outcome === "callback_needed");
  if (q) {
    const n = q.toLowerCase();
    cards = cards.filter(
      (c) =>
        (c.customer_name ?? "").toLowerCase().includes(n) ||
        (c.summary ?? "").toLowerCase().includes(n) ||
        c.phone_masked.includes(n),
    );
  }
  return cards;
}

export async function getSummary(): Promise<Summary> {
  if (isDemo()) return DEMO_SUMMARY;
  return (await authedFetch<Summary>("/api/reports/summary")) ?? EMPTY_SUMMARY;
}

export async function startOutbound(phone: string, name?: string): Promise<{ ok: boolean }> {
  const res = await authedFetch<unknown>("/api/call_sessions/outbound", {
    method: "POST",
    body: JSON.stringify({ phone, customer_name: name ?? null }),
  });
  return { ok: res !== null };
}

/** Open the live feed socket. Calls onEvent for each pushed update. Returns a cleanup fn. */
export function connectFeedSocket(onEvent: (msg: unknown) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  (async () => {
    const token = await ensureToken();
    if (!token || closed) return;
    const url = `${BASE.replace(/^http/, "ws")}/api/ws?token=${encodeURIComponent(token)}`;
    ws = new WebSocket(url);
    ws.onmessage = (e) => {
      try {
        onEvent(JSON.parse(e.data));
      } catch {
        /* ignore non-JSON */
      }
    };
  })();
  return () => {
    closed = true;
    ws?.close();
  };
}

/** Presigned playback URL for a call's recording (null if none / backend unreachable). */
export async function getRecordingUrl(callSessionId: string): Promise<string | null> {
  const res = await authedFetch<{ url: string }>(`/api/call_sessions/${callSessionId}/recording`);
  return res?.url ?? null;
}
