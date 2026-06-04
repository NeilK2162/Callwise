# Callwise — Frontend

Next.js (App Router) · TypeScript · Tailwind. Two surfaces:

- **`/`** — the landing page (the conversion asset, PRD §18.2): outcome headline + a
  "📞 Call the agent now" CTA, the missed-call ROI math, how-it-works, a dashboard
  preview, an example query card, and pricing.
- **`/dashboard`** — the clinic dashboard (PRD §0.5): a stats bar, filters + search, and a
  live feed of **query cards**. Click any card for the detail slide-out (transcript,
  recording, extracted fields). The **Start Outbound Call** button opens the trigger modal.

## Dev

```bash
npm install
npm run dev          # http://localhost:3000
```

The dashboard reads from the control-plane API at `NEXT_PUBLIC_API_BASE_URL`, and **falls
back to seeded example calls** (`mocks/seed.ts`) when the API is unreachable — so the feed
always looks alive, even before the backend is running (PRD §0.6).

## Layout

```
app/
  layout.tsx              # root shell + fonts
  globals.css             # tailwind layers
  (marketing)/page.tsx    # landing page
  dashboard/page.tsx      # the feed
components/
  StatsBar · Filters · QueryCard · CardDetail · OutboundModal
lib/
  types.ts · api.ts       # API client with seed fallback
mocks/
  seed.ts                 # pre-seeded example query cards
```
