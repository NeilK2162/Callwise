# Callwise

> An AI voice agent that answers inbound calls, makes outbound follow-ups, and turns every
> conversation into a clean, tagged query in one dashboard — and **books real appointments
> live on the call**.

A caller dials your number → an AI receptionist answers in a natural voice (Soniox STT →
LLM → ElevenLabs TTS over LiveKit) → it checks your real calendar, books the appointment on
**Cal.com** during the call, and confirms → the call lands in the dashboard as a tagged,
searchable **query card** with the transcript, recording, and the booking details.

The full engineering spec is `PRD_Callwise_Production.md` (untracked).

---

## How a real call flows

```
 Caller's phone
      │  PSTN
      ▼
 Twilio number ──(Elastic SIP Trunk)──► LiveKit SIP ──► LiveKit room
                                                            │ dispatch rule → agent_name
                                                            ▼
                       ┌──────────────────────────────────────────────┐
                       │  Callwise voice agent (livekit_agent.py)      │
                       │  Soniox STT → LLM (OpenAI/Anthropic) → 11Labs │
                       │  tools: check_availability · book_appointment │──► Cal.com (live booking)
                       └───────────────────────┬──────────────────────┘
                                               │ on hangup: POST transcript + booking
                                               ▼
                 webhook-ingest ─► verify worker (LLM tag + extract) ─► query card
                                                               │ live WS push
                                                               ▼
                                                         Dashboard feed
```

The same `verify → tag → card` pipeline serves every provider; the mock provider (below)
exercises it with zero credentials for local dev, CI, and load tests.

---

## What you need to go live (bring these credentials)

| Service | Used for | You provide | Where it's set |
|---|---|---|---|
| **Twilio** | The phone number (DID) + PSTN | Account SID, Auth Token, **a purchased number**, an **Elastic SIP Trunk** pointed at LiveKit | Twilio console |
| **LiveKit Cloud** | Real-time media, SIP, agent runtime | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` + an **inbound SIP trunk + dispatch rule** | LiveKit Cloud + `lk` CLI |
| **Soniox** | Speech-to-text (STT) | `SONIOX_API_KEY` | console.soniox.com |
| **ElevenLabs** | Text-to-speech (TTS) voice | `ELEVEN_API_KEY` + a `ELEVENLABS_VOICE_ID` | elevenlabs.io |
| **OpenAI** *or* **Anthropic** | The conversation brain + post-call verification | `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) | platform.openai.com / console.anthropic.com |
| **Cal.com** | Live appointment booking | `CALCOM_API_KEY` (`cal_…`) + `CALCOM_EVENT_TYPE_ID` (numeric) | cal.com → Settings → Developer → API keys; event-type id from the event-type URL/API |
| Postgres · Redis · S3 | Data, queues, recordings | local via `docker compose` (Postgres, Redis, MinIO) — or managed (RDS / ElastiCache / S3) | `.env` |

> Twilio is only the *carrier* here. LiveKit Cloud also sells phone numbers directly
> ([LiveKit Phone Numbers](https://docs.livekit.io/telephony/start/phone-numbers)) — if you
> use one, you can skip the Twilio SIP-trunk step entirely.

---

## Go-live setup (≈ 30 minutes)

### 1. Bring up infrastructure + the API/workers

```bash
cp .env.example .env          # then fill in the real keys from the table above
docker compose up -d postgres pgbouncer redis minio
docker compose run --rm migrate                       # create the schema
docker compose run --rm seed                          # demo user + a "Bright Smile Dental" campaign
docker compose up -d control-api webhook-ingest dialer-worker verification-worker reconciler ingest-worker
```

Grab the campaign id (login `demo@callwise.local` / `demo12345`, `GET /api/campaigns`) and
set **`INBOUND_CAMPAIGN_ID`** in `.env` so inbound calls are attributed to it, then
`docker compose up -d verification-worker` again.

> The webhook-ingest service must be reachable from the agent at `BASE_URL`. Locally, run the
> agent on the same host (`BASE_URL=http://localhost:8001`); in the cloud, set `BASE_URL` to
> its public URL.

### 2. LiveKit — SIP trunk + agent dispatch

Create a LiveKit Cloud project; copy `LIVEKIT_URL/API_KEY/API_SECRET` into `.env`. Then
([accepting calls](https://docs.livekit.io/sip/accepting-calls)):

```bash
lk sip inbound-trunk create   # an inbound trunk (restrict to your Twilio IPs/number)
lk sip dispatch-rule create   # dispatch inbound calls to a room AND dispatch agent_name=callwise-agent
```

The dispatch rule's `agent_name` must equal `LIVEKIT_AGENT_NAME` (default `callwise-agent`).

### 3. Twilio — point the number at LiveKit

In Twilio: **Elastic SIP Trunking → create a trunk → Origination** → add the LiveKit SIP URI
(`sip:<your-project>.sip.livekit.cloud`), then route your purchased number to that trunk.
(LiveKit's [SIP trunk setup](https://docs.livekit.io/telephony/start/sip-trunk-setup) has
the exact Twilio screens.)

### 4. Cal.com — the calendar the agent books into

Create an event type (e.g. "New patient consult"), note its **numeric event-type id**, and
create an API key. Set `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`, `CALCOM_TIMEZONE`.

### 5. Run the voice agent (separate process, needs the `conversation` extra)

```bash
cd backend
uv sync --extra conversation --extra llm     # livekit-agents[soniox,elevenlabs,silero,openai,anthropic]
uv run python -m callwise.providers.conversation.livekit_agent download-files   # one-time: VAD model
uv run python -m callwise.providers.conversation.livekit_agent start
```

It registers with LiveKit and waits for dispatched calls.

### 6. Dashboard

```bash
cd frontend && npm install && npm run dev      # http://localhost:3000/dashboard
```

The dashboard auto-logs-in as the demo user and shows **real** data (empty until your first
call). No mock/seed data in the live path.

---

## The demo (what a user actually experiences)

1. **Call your Twilio number** from your phone.
2. The agent answers: *"Thanks for calling Bright Smile Dental — this is an automated
   assistant. How can I help?"*
3. Ask to book. It reads **real open Cal.com slots**, takes your name + email, confirms a
   slot, and **books it live** (real Cal.com booking + confirmation email): *"Booked you for
   Saturday 11 AM — confirmation sent."*
4. Hang up. Within seconds a **query card** slides into the dashboard: caller, one-line
   summary, `✅ Appointment Booked`, the extracted name/date + Cal.com confirmation, the full
   transcript, and the recording.

**Outbound** ("Start Outbound Call" in the dashboard) places a call through the same governed
dial path; for the LiveKit voice path it requires a LiveKit outbound SIP trunk (see
[making calls](https://docs.livekit.io/sip/making-calls)).

---

## Local dev & tests (no credentials)

`TELEPHONY_PROVIDER=mock` / `CONVERSATION_PROVIDER=mock` / `LLM_PROVIDER=mock` (compose
default) simulate the whole pipeline so you can develop, run the load/chaos harness, and run
the test suite offline. Mock is **test-only infrastructure** — it never serves the live demo.

```bash
cd backend && uv sync
uv run ruff check . && uv run pytest -q          # 68 unit tests; idempotency suite runs in CI
```

---

## Repository layout

```
backend/   FastAPI control-API + webhook-ingest, workers (dialer/verification/reconciler/ingest),
           the voice agent (providers/conversation/livekit_agent.py), booking.py (Cal.com),
           governors, idempotency, providers (telephony/conversation/llm), storage (S3).
frontend/  Next.js dashboard (real data) + landing page.
infra/     Kubernetes + KEDA, PgBouncer, Redis.
docs/      architecture · data-model · idempotency · vendors (every credential + doc link) · runbooks.
```

See [`docs/vendors.md`](docs/vendors.md) for the full vendor → status → credential matrix and
[`docs/architecture.md`](docs/architecture.md) for the system design + cost controls.

---

## The principles

> **Initiations are elastic; live calls are sacred.** Under stress the system stops *starting*
> calls (sheds at the queue) but never drops a live call or loses its record.
>
> **Spend tokens only where they change the outcome.** One LLM call per answered call
> (classify + extract + summarize together), trimmed transcript, behind a per-minute token
> budget and a per-campaign spend ceiling (PRD §19).
