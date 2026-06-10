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

Grab the campaign id (login `demo@callwise.dev` / `demo12345`, `GET /api/campaigns`) and
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

## Faster path for the demo: ElevenLabs Agent (hosted Qwen + TTS + turn-taking)

The LiveKit setup above lets you **own the whole stack** (and keep Soniox STT). But for a
*demo*, ElevenLabs' Agents platform wins on three axes at once — it hosts the **LLM**
(`Qwen3-30b-a3b`, sub-150 ms time-to-first-sentence), the **TTS**, and a **turn-taking** model
that's faster and more accurate than a hand-tuned LiveKit VAD loop, all co-located in one
datacenter. The only thing you give up is configuring the tools in their portal instead of in
code.

**This is not throwaway.** ElevenLabs becomes a thin front-end: every tool is a webhook into
*your* backend (`/api/v2/agent-tools/*` → `callwise.agent_tools`, the same logic the LiveKit
agent runs), and the call still becomes a query card through the **same** post-call webhook +
verify pipeline. To move to production you flip `CONVERSATION_PROVIDER` back to `livekit` —
**zero** booking/pipeline code changes. (STT on this path is ElevenLabs' own; Soniox is used on
the LiveKit path.)

```
 Caller ─PSTN─► Twilio number ─► ElevenLabs Agent (Qwen LLM · TTS · turn-taking)
                                      │  mid-call tool calls (HTTPS + shared secret)
                                      ▼
              {BASE_URL}/api/v2/agent-tools/{check-availability,book-appointment,…}
                                      │  → callwise.agent_tools → Cal.com (live booking)
                                      ▼  outcome stashed by conversation_id (Redis)
              on hangup: POST /api/v2/webhooks/elevenlabs (HMAC) ─► verify worker ─► query card
```

### What you actually need (and what you don't)

The "go live" table near the top is the full **LiveKit** path. The ElevenLabs demo needs far
less — most of it lives in the ElevenLabs portal, not your `.env`:

| What | For | Goes in |
|---|---|---|
| **ElevenLabs** account + one Agent | the whole conversation — LLM (`Qwen3-30b-a3b`), TTS, STT, turn-taking, all hosted | ElevenLabs portal |
| **Twilio** number + Account SID / Auth Token | the phone number | **the ElevenLabs portal** (import) — *not* your `.env` |
| **Cal.com** API key + numeric event-type id | live booking | `.env` → `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`, `CALCOM_TIMEZONE` |
| **A secret you invent** (32+ chars) | auth on every agent→backend tool call | `.env` → `AGENT_TOOLS_SECRET` (same value in the portal tool header) |
| **ElevenLabs post-call signing secret** | verify the post-call webhook | `.env` → `ELEVENLABS_WEBHOOK_SECRET` |
| **A public URL** (cloudflared / ngrok) | so ElevenLabs can reach your tools + webhook | `.env` → `BASE_URL` |
| Postgres · Redis · MinIO | data · queue/stash · recordings | local `docker compose` — **no keys** |

**Optional — nicer cards, not required:** `OPENAI_API_KEY` with `LLM_PROVIDER=openai` gives
richer auto-tagging/summaries on calls where no tool fired. Leave it at `LLM_PROVIDER=mock` and
the demo still works perfectly — booking / callback / opt-out outcomes come from the agent's
tool calls, and the card summary uses ElevenLabs' own transcript summary.

**You do NOT need for this demo:** `LIVEKIT_*`, `SONIOX_API_KEY`, `ELEVEN_API_KEY` /
`ELEVENLABS_VOICE_ID` in `.env` (the voice is chosen in the portal), or Twilio creds in `.env`.

> **One required setting:** the verify worker parses post-call payloads with the configured
> conversation provider — set **`CONVERSATION_PROVIDER=elevenlabs`** for the demo, or it will
> try to parse ElevenLabs payloads with the wrong parser.

Minimal `.env` for the demo:

```bash
APP_ENV=dev
BASE_URL=https://<your-tunnel>.trycloudflare.com   # public URL ElevenLabs can reach
CONVERSATION_PROVIDER=elevenlabs                    # so the verifier uses the ElevenLabs parser
LLM_PROVIDER=mock                                   # or: openai (+ OPENAI_API_KEY) for richer tags
CALCOM_API_KEY=cal_xxxxxxxx
CALCOM_EVENT_TYPE_ID=123456
CALCOM_TIMEZONE=Asia/Kolkata
AGENT_TOOLS_SECRET=<32+ char random>               # also set as the tool header in the portal
ELEVENLABS_WEBHOOK_SECRET=<from the ElevenLabs post-call webhook>
INBOUND_CAMPAIGN_ID=<campaign uuid from /api/campaigns>   # optional; else the newest campaign
# JWT_SECRET / CONTEXT_TOKEN_SECRET: dev defaults pass startup; set real 32+ char values for a public demo
```

### Setup (≈ 15 minutes)

1. **Infra + API/workers, publicly reachable.** Do step 1 above, then expose the
   webhook-ingest service so ElevenLabs can reach it and set `BASE_URL` to that URL:
   ```bash
   cloudflared tunnel --url http://localhost:8001     # or: ngrok http 8001
   # put the https URL in .env as BASE_URL, then restart webhook-ingest + verification-worker
   ```
   Set `CALCOM_API_KEY` + `CALCOM_EVENT_TYPE_ID` (so booking works) and a strong
   `AGENT_TOOLS_SECRET` (the shared secret below).

2. **Create the agent** (ElevenLabs → Agents → create). Paste the receptionist policy from
   [`docs/agent-conversation.md`](docs/agent-conversation.md) as the system prompt. Set
   **LLM = `Qwen3-30b-a3b`**, **TTS voice = your `ELEVENLABS_VOICE_ID`** (use the
   `eleven_flash_v2_5` model for lowest latency), language English.

3. **Add four server tools** (Agent → Tools → Add tool → **Webhook**). Each is a `POST` to the
   URL below with header `X-Callwise-Agent-Secret: <AGENT_TOOLS_SECRET>`. Give every tool a
   `conversation_id` and `caller_id` parameter bound to the agent's **system variables** so
   outcomes attach to the call and the desk gets a callback number:

   | Tool (description for the LLM) | `POST {BASE_URL}` | Body parameters |
   |---|---|---|
   | **check_availability** — read the next open slots (caller is flexible) | `/api/v2/agent-tools/check-availability` | `preference?`, `conversation_id`, `caller_id` |
   | **check_time** — is a *specific* requested time open? confirms it or offers the nearest alternatives | `/api/v2/agent-tools/check-time` | `desired_iso` (ISO-8601), `conversation_id`, `caller_id` |
   | **book_appointment** — book after the caller confirms a slot + you read their name/email back | `/api/v2/agent-tools/book-appointment` | `name`, `email`, `slot_iso`, `conversation_id`, `caller_id` |
   | **take_message** — no time / no email / reschedule / cancel / wants human / question | `/api/v2/agent-tools/take-message` | `name`, `reason`, `details?`, `callback_window?`, `conversation_id`, `caller_id` |
   | **mark_do_not_contact** — "stop calling me" | `/api/v2/agent-tools/do-not-contact` | `conversation_id`, `caller_id` |

   Bind `conversation_id = {{system__conversation_id}}` and `caller_id = {{system__caller_id}}`
   (confirm the exact names in the portal's system-variables list). Each tool returns
   `{"say": …}` — the line the agent speaks; `check_availability` / `check_time` also return
   `slots[]` with the `slot_iso` to pass back into `book_appointment`. In the prompt, tell the
   agent to call **check_time** when the caller names a specific time (e.g. "Thursday at 3")
   and **check_availability** when they're flexible — `check_time` does a real point-in-time
   Cal.com query for that day and either confirms it or offers the nearest open times.

4. **Post-call webhook** (ElevenLabs → workspace webhooks → add `post_call_transcription`):
   point it at `{BASE_URL}/api/v2/webhooks/elevenlabs`, copy the signing secret into
   `ELEVENLABS_WEBHOOK_SECRET`, restart the verification worker. This is what turns the call
   into a query card (with the real Cal.com booking uid, via the stashed outcome).

5. **Connect the Twilio number** (ElevenLabs → Phone numbers → import from Twilio; provide your
   Twilio SID/Token) and assign this agent for **inbound** calls. No SIP trunk to configure —
   ElevenLabs manages the media.

Now call the number. Same demo as below — the card lands via the ElevenLabs path instead of
LiveKit, and `INBOUND_CAMPAIGN_ID` still controls attribution.

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
