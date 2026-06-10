# Callwise — Demo Setup (ElevenLabs Agent)

> Stand up the full Callwise demo: a real **inbound AI receptionist** that books live
> **Cal.com** appointments and turns every call into a tagged **query card** in the dashboard —
> with **ElevenLabs** running the conversation (hosted **Qwen** LLM + TTS + turn-taking, all
> co-located for low latency). End to end in ~20 minutes.
>
> This is the **fast demo path**. To own the whole stack (LiveKit + Soniox) for production, see
> [`README.md`](README.md) — you don't need any of that here.

Follow the parts in order: **Cal.com → Backend → ElevenLabs → Dashboard → Call.**

---

## How a call flows

```
 Caller's phone ─PSTN─► Twilio number ─► ElevenLabs Agent  (Qwen LLM · TTS · turn-taking)
                                              │  mid-call tool calls (HTTPS + shared secret)
                                              ▼
   {BASE_URL}/api/v2/agent-tools/{check-availability · check-time · book-appointment · …}
                                              │  → Cal.com (live booking)
                                              ▼  outcome stashed by conversation_id (Redis)
   on hangup → POST {BASE_URL}/api/v2/webhooks/elevenlabs (HMAC) ─► verify worker ─► query card ─► dashboard
```

ElevenLabs runs the voice and **calls your backend's tools**; your backend owns the booking and
the dashboard. The call becomes a card automatically.

---

## What you need (and what you don't)

| What | For | Goes where |
|---|---|---|
| **Cal.com** account → API key + a numeric event-type id | live booking | `.env` |
| **ElevenLabs** account + one Agent | the whole conversation (Qwen LLM, TTS, STT, turn-taking — all hosted) | ElevenLabs portal |
| **Twilio** number + Account SID / Auth Token | the phone number | **imported into the ElevenLabs portal** — *not* your `.env` |
| **A secret you invent** (32+ chars) | auth on every agent→backend tool call | `.env` + the portal tool header |
| **ElevenLabs post-call signing secret** | verify the post-call webhook | `.env` |
| **A public URL** (cloudflared / ngrok) | so ElevenLabs can reach your tools + webhook | `.env` (`BASE_URL`) |
| **Docker** (Postgres · Redis · MinIO) | data · queue/stash · recordings | local — **no keys** |

**You do NOT need:** LiveKit, Soniox, `ELEVEN_API_KEY` / voice id in `.env` (the voice is chosen
in the portal), or Twilio creds in `.env`.

**Optional — nicer cards, not required:** `OPENAI_API_KEY` with `LLM_PROVIDER=openai` gives
richer auto-tagging/summaries on calls where no tool fired. Leave it at `LLM_PROVIDER=mock` and
the demo still works — booking / callback / opt-out outcomes come from the agent's tool calls,
and the card summary uses ElevenLabs' own transcript summary.

---

# Part 1 — Cal.com (the calendar the agent books into)

### 1.1 Create an account and an event type
1. Sign up at **[cal.com](https://cal.com)** and finish onboarding (connect a calendar if you
   want real conflicts respected — optional for the demo).
2. **Event Types → + New** and fill in the event exactly like this (matches the Bright Smile
   Dental demo):

   | Field | Value |
   |---|---|
   | **Title** | `New patient consult` |
   | **Description** | `New patient consulting appointment in Clinic on` |
   | **URL** | `new-patient-consult` |
   | **Duration** | `30` minutes |
   | **Allow multiple durations** | off (single 30-min slot is enough for the demo) |
   | **Location** | **In Person (Organizer Address)** → `Madhapur, Hyderabad` |
   | **Display on booking page** | on |

   Click **Save**. (Phone call or a conferencing app also works if you prefer — the agent books
   by API; location is what shows on the Cal.com confirmation.)
3. **Availability:** open **Availability** and make sure you have **open hours in the next 7
   days**. If the calendar has no open slots, `check_availability` returns nothing and the agent
   will (correctly) offer to take a message instead of booking — so give yourself some slots.

#### Event-type settings that matter (and what to skip)

The agent books over the API and sends only **name + email** (+ optional phone). So the goal is:
don't require anything else, and make bookings confirm instantly. Set these tabs:

| Tab | Set it to | Why |
|---|---|---|
| **Booking form** | Keep **only Name + Email** required. Do **not** add required custom questions. | The agent sends only name + email — an extra *required* field makes the API booking fail (the agent would then wrongly say "that time's taken"). |
| **Booking experience** / Advanced | **"Requires confirmation" → OFF** | So bookings are **auto-confirmed** (matches the agent saying "booked, confirmation sent"). ON makes them *pending*. |
| **Limits & buffers** | **Minimum notice → low** (0–2 h) | So you can book *during* the call. A large minimum notice hides all near-term slots. |
| **Privacy & security** | Booker **email verification → OFF** | The API books directly; a verification step would block it. |
| **Seats** | **OFF** (decline the "Offer seats" prompt) | Seats change the booking model and disable normal bookings. |
| **Recurring** | **OFF** | Single one-off appointment. |
| **Availability** | A schedule with **open days in the next 7 days** (you've done this) | `check_availability` queries the next 7 days; no slots → the agent takes a message instead. |

Your **Location = In Person (Organizer Address)** is ideal — it needs no input from the booker.
Avoid location types that ask the *booker* for something (e.g. "Attendee phone number"), since
the API booking doesn't supply those.

**Leave as default / skip for the demo:** Basics, Confirmation (unless you want a custom redirect
page), Appearance, Apps, AI & Automation, Webhooks. **Workflows** is optional — add an SMS/email
reminder there if you want extra realism, but it's not needed.

### 1.2 Find the numeric event-type id → `CALCOM_EVENT_TYPE_ID`
- Open the event type for editing and look at the browser URL — the number is the id:
  `https://app.cal.com/event-types/`**`123456`**`?tabName=setup` → `CALCOM_EVENT_TYPE_ID=123456`.
- Or list them via the API once you have a key (1.3):
  ```bash
  curl -s https://api.cal.com/v2/event-types \
    -H "Authorization: Bearer $CALCOM_API_KEY" -H "cal-api-version: 2024-06-14" | jq '.data[] | {id, slug, lengthInMinutes}'
  ```

### 1.3 Create an API key → `CALCOM_API_KEY`
- **Settings → Security → API Keys** (older UIs: **Settings → Developer → API Keys**) →
  **+ Add**. Name it "Callwise", set expiry to **Never** (or far out), **Save**, and copy the
  key — it starts with **`cal_live_…`**. You only see it once.

### 1.4 Timezone → `CALCOM_TIMEZONE`
- Use your clinic's IANA timezone, e.g. `Asia/Kolkata`. Slots are matched in this timezone, so a
  caller saying "3 PM" resolves against it.

> **You now have:** `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`, `CALCOM_TIMEZONE`. Cal.com sends
> the confirmation email automatically when the agent books — that's the "confirmation sent" the
> agent promises on the call.

---

# Part 2 — Backend (your machine)

### 2.1 Configure `.env`

```bash
cp .env.example .env
```

Set just these (everything else — Postgres/Redis/S3 — uses the docker-compose dev defaults):

```bash
APP_ENV=dev
BASE_URL=https://<your-tunnel>.trycloudflare.com   # filled in step 2.3
CONVERSATION_PROVIDER=elevenlabs                    # REQUIRED — the verifier uses the ElevenLabs parser
LLM_PROVIDER=mock                                   # or: openai (+ OPENAI_API_KEY) for richer tags
CALCOM_API_KEY=cal_live_xxxxxxxx                    # from Part 1.3
CALCOM_EVENT_TYPE_ID=123456                         # from Part 1.2
CALCOM_TIMEZONE=Asia/Kolkata                        # from Part 1.4
AGENT_TOOLS_SECRET=<32+ char random>                # invent one; also set in the portal (Part 3.2)
ELEVENLABS_WEBHOOK_SECRET=<from ElevenLabs>         # from Part 3.4
INBOUND_CAMPAIGN_ID=                                # optional; blank = newest campaign (the seeded one)
# JWT_SECRET / CONTEXT_TOKEN_SECRET: dev defaults pass startup; set real 32+ char values for a public demo
```

Generate a secret quickly (PowerShell): `[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')`.

### 2.2 Bring up the stack

```bash
docker compose up -d postgres pgbouncer redis minio
docker compose run --rm migrate                     # create the schema
docker compose run --rm seed                        # demo user (demo@callwise.dev / demo12345) + a campaign
docker compose up -d --build control-api webhook-ingest verification-worker reconciler ingest-worker
```

(`dialer-worker` is only for *outbound* calls — skip it for the inbound demo.)

> **Why `--build`:** without it Docker can boot a **stale image** missing newer code (e.g. the
> `agent-tools` routes), and tool calls will then 404. After any backend change, re-run with `--build`.

### 2.3 Expose it publicly

ElevenLabs must reach your tools + webhook, so put the **webhook-ingest** service (default
`:8001`, this is your `BASE_URL`) behind a public URL:

```powershell
.\tunnel.ps1
# First run downloads cloudflared (no admin, no PATH change), then starts the tunnel.
# Blocked by execution policy?  powershell -ExecutionPolicy Bypass -File .\tunnel.ps1
# Already have cloudflared on PATH?  cloudflared tunnel --url http://localhost:8001   (or: ngrok http 8001)
```

Copy the printed `https://…trycloudflare.com` into `BASE_URL` in `.env`, then restart the
services that read it:

```bash
docker compose up -d webhook-ingest verification-worker
```

> The quick-tunnel URL is **random and changes on every restart** — keep the window open during
> the demo. If it does change: update `BASE_URL` in `.env`, restart the two services above,
> **re-run `.\elevenlabs_tools.ps1`** (fixes all five tool URLs in one shot), and update the
> post-call webhook URL in the portal.

### 2.4 Pre-flight check (no phone needed)

Confirm Cal.com + the tool auth work *before* wiring ElevenLabs. **On Windows, use
`Invoke-RestMethod`** — `curl.exe` quoting and `<…>` placeholders misbehave in PowerShell:

```powershell
$secret = '<the same value as AGENT_TOOLS_SECRET in .env>'
Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/api/v2/agent-tools/check-availability' -Headers @{ 'X-Callwise-Agent-Secret' = $secret } -ContentType 'application/json' -Body '{"conversation_id":"preflight"}'
```

macOS / Linux:

```bash
curl -X POST "$BASE_URL/api/v2/agent-tools/check-availability" \
  -H "X-Callwise-Agent-Secret: $AGENT_TOOLS_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"preflight"}'
# expect:  {"say":"Open times: …","status":"ok","slots":[ … ]}
```

Real slots back → the hard part works. (`401` = secret mismatch; `"status":"error"` about the
calendar = `CALCOM_*` wrong; `"status":"no_slots"` = add availability in Cal.com, Part 1.1; **`404` / `Not Found` = stale image** — rebuild with `--build` (Part 2.2).)

---

# Part 3 — ElevenLabs agent

Portal: **[elevenlabs.io](https://elevenlabs.io) → Agents** (a.k.a. ElevenAgents / Conversational AI).

> ### 🔑 The two secrets — don't mix them up
> | | **Secret A — `AGENT_TOOLS_SECRET`** | **Secret B — `ELEVENLABS_WEBHOOK_SECRET`** |
> |---|---|---|
> | Who creates it | **You** (you invented it; it's already in your `.env`) | **ElevenLabs** (generated when you create the post-call webhook, 3.4) |
> | Direction | your `.env` ➜ **into the portal** | the portal ➜ **into your `.env`** |
> | Where in the portal | header `X-Callwise-Agent-Secret` on each of the 5 tools (stored once as workspace secret `callwise_agent_secret`, step 3.2) | shown once when you create the post-call webhook — copy it out |
> | What it protects | your backend trusts the agent's **mid-call tool calls** | your backend trusts the **post-call transcript** webhook |
> | After setting it | nothing to restart (portal-side) | `docker compose up -d webhook-ingest` |
>
> Until Secret B is filled in, dev mode (`APP_ENV=dev`) accepts the post-call webhook unsigned —
> so you can demo before creating it; just don't leave a placeholder value in `.env`.

> ⚠️ **Tunnel check before you paste URLs:** quick-tunnel URLs die on every restart. Use the
> `https://….trycloudflare.com` your tunnel window shows **right now** for every URL below, and
> sanity-check it first: `https://<current-tunnel>/api/v2/health` → `{"status":"ok"}`.

### 3.1 Create the agent and its "brain"

1. **Agents → + Create agent** → start blank. Name it "Callwise Receptionist".
2. **System prompt:** paste the receptionist policy from
   [`docs/agent-conversation.md`](docs/agent-conversation.md) (it covers the greeting + every
   edge case). Add one routing line at the end:
   > *Call **check_time** when the caller names a specific time (e.g. "Thursday at 3"); call
   > **check_availability** when they're flexible. Read names/emails back before booking. Never
   > read IDs or times in ISO format aloud.*
3. **First message** (greeting): *"Thanks for calling Bright Smile Dental — this is an automated
   assistant, and this call may be recorded. How can I help you today?"*
4. **LLM / Model:** select **`Qwen3-30b-a3b`** from the model dropdown (ElevenLabs-hosted).
5. **Voice / TTS:** pick a voice; set the model to **`Eleven Flash v2.5`** for the lowest latency.
6. **Language:** English. Save.

### 3.2 Store the tool secret (do this once)

Your backend rejects tool calls that don't carry the right secret. Store it in ElevenLabs as a
**workspace secret**, then reference it in tool headers:

- In the agent's **Tools / Security** area, when you add the first tool header (next step),
  choose header type **Secret → Create New Secret**, name it **`callwise_agent_secret`**, and
  paste the **same value** as `AGENT_TOOLS_SECRET` from your `.env`.
- It's then referenced anywhere as `{{secret__callwise_agent_secret}}`.

### 3.3 Add the five server tools

> ### ⚡ Recommended: create them by script, not by hand
> The repo ships [`elevenlabs_tools.ps1`](elevenlabs_tools.ps1), which creates (or updates) all
> five tools through ElevenLabs' public API — correctly shaped, with your tunnel URL and secret
> read straight from `.env`:
> ```powershell
> $env:ELEVENLABS_API_KEY = 'sk_...'    # ElevenLabs profile → API Keys
> .\elevenlabs_tools.ps1                 # five CREATED/UPDATED lines expected
> ```
> Then in the portal: **agent → Tools → Add tool → pick the five workspace tools** it created,
> and hit **Test** on `check_availability` (expect real Cal.com slots). **Re-run the script any
> time the tunnel URL changes** — it patches all five URLs in one shot.
>
> Why script-first: the portal's JSON editor uses an internal format that rejects valid API
> JSON ("failed to create tool"), and the API enforces a non-obvious rule — a body param may
> carry **only one** of `description` / `dynamic_variable` / `constant_value`. The script
> already encodes all of this. The manual steps below remain as reference / fallback.

**Manual fallback — Agent → Tools → Add tool → Webhook**, once per tool. **Common settings for all five:**

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `{BASE_URL}/api/v2/agent-tools/<endpoint>` (table below) |
| Header 1 | `Content-Type: application/json` |
| Header 2 | `X-Callwise-Agent-Secret: {{secret__callwise_agent_secret}}` |
| Response handling | the agent speaks the returned **`say`** field |

**Parameters come in two kinds — the Value Type dropdown is the key:**

- Conversation-filled params (`name`, `email`, `slot_iso`, …) → Value Type **LLM Prompt**. The
  model fills them from the call, guided by your **Description** text — write those carefully.
- The two plumbing params below → Value Type **Dynamic variable**, with the value typed in
  double curly braces. **Every tool gets both** (they attach outcomes to the call and give the
  desk a callback number):

| Parameter | Data type | Value Type | Value |
|---|---|---|---|
| `conversation_id` | string | Dynamic variable | `{{system__conversation_id}}` |
| `caller_id` | string | Dynamic variable | `{{system__caller_id}}` |

**Per-tool endpoint + the parameters the LLM fills from the conversation:**

| Tool name (+ description for the LLM) | Endpoint | LLM-filled parameters |
|---|---|---|
| **check_availability** — read the next open slots when the caller is flexible | `/api/v2/agent-tools/check-availability` | `preference` (string, optional — e.g. "Saturday morning") |
| **check_time** — check whether ONE specific requested time is open; confirms it or offers the nearest alternatives | `/api/v2/agent-tools/check-time` | `desired_iso` (string, required — ISO-8601 of the time the caller asked for) |
| **book_appointment** — book after the caller confirms a slot and you've read their name + email back | `/api/v2/agent-tools/book-appointment` | `name` (string), `email` (string), `slot_iso` (string — the `slot_iso` returned by check_availability/check_time) |
| **take_message** — no suitable time / won't give email / reschedule / cancel / wants a human / unanswered question | `/api/v2/agent-tools/take-message` | `name` (string), `reason` (string: `no_suitable_time` \| `book_no_email` \| `reschedule` \| `cancel` \| `wants_human` \| `question`), `details` (string, optional), `callback_window` (string, optional) |
| **mark_do_not_contact** — caller says "stop calling me" / remove me | `/api/v2/agent-tools/do-not-contact` | *(none beyond the two system params)* |

**Worked example — `book_appointment`** (what you type into the portal):

- Name: `book_appointment`
- Description: *"Book the appointment after the caller has confirmed a specific slot and you have read their full name and email back to them."*
- Method `POST`, URL `{BASE_URL}/api/v2/agent-tools/book-appointment`
- Headers: `Content-Type: application/json`, `X-Callwise-Agent-Secret: {{secret__callwise_agent_secret}}`
- Body parameters:
  | Name | Type | Required | Description / Value |
  |---|---|---|---|
  | `name` | string | yes | Caller's full name |
  | `email` | string | yes | Caller's email, already confirmed by reading it back |
  | `slot_iso` | string | yes | The chosen slot's ISO start, exactly as returned by check_availability/check_time |
  | `conversation_id` | string | yes | Value Type **Dynamic variable** → `{{system__conversation_id}}` |
  | `caller_id` | string | yes | Value Type **Dynamic variable** → `{{system__caller_id}}` |

  (`name`/`email`/`slot_iso` stay on Value Type **LLM Prompt** — the description text above is
  what guides the model.)

Each tool returns `{"say": "...", "status": "..."}`; `check_availability` and `check_time` also
return `slots[]`, each with the `slot_iso` to pass into `book_appointment`.

### 3.4 Post-call webhook → `ELEVENLABS_WEBHOOK_SECRET`

This is what turns each finished call into a query card. It lives on the **Agents Platform
settings page** (not the agent itself): **[elevenlabs.io/app/agents/settings](https://elevenlabs.io/app/agents/settings)**.

1. Open **Agents → Settings → Post-call webhooks** → **Create / Add webhook**.
2. Type: **`post_call_transcription`** (skip `post_call_audio` / `call_initiation_failure`) ·
   URL: **`{BASE_URL}/api/v2/webhooks/elevenlabs`** (your *current* tunnel URL) · Auth: **HMAC**.
3. ElevenLabs shows a **signing secret on creation (Secret B — shown once)**. Copy it into
   `ELEVENLABS_WEBHOOK_SECRET` in `.env`, then recreate the service that checks it:
   `docker compose up -d webhook-ingest`.
4. The webhook applies workspace-wide (all agents); per-agent overrides exist in the agent's
   webhook settings if you ever need them. Nothing else to enable for the demo.

### 3.5 Connect the Twilio number

1. **Phone numbers → Import a number → Twilio.**
2. Enter your **Twilio Account SID + Auth Token** and the **number** (E.164, e.g. `+1…`).
3. Assign **this agent** to handle **inbound** calls on that number. No SIP trunk to configure —
   ElevenLabs manages the media.

---

# Part 4 — Dashboard

```bash
cd frontend && npm install && npm run dev    # http://localhost:3000/dashboard
```

Auto-logs in as the demo user (`demo@callwise.dev`). Empty until your first call — that's
correct (no mock data in the live path).

---

## ✅ Make the call

1. **Call your Twilio number.** The agent answers with your greeting.
2. **Book flexibly:** "What've you got this week?" → it reads real Cal.com slots, takes your name
   + email (reads them back), and **books live** → *"Booked you for Saturday 11 AM — confirmation
   sent."* (check your inbox for the Cal.com email.)
3. **Hang up.** Within seconds a **query card** appears: caller, one-line summary,
   `✅ Appointment Booked`, the extracted name/date + Cal.com confirmation, the transcript.

**You're done when that card lands.** Then show off the edge cases:
- Name a taken time → it offers the nearest alternatives (`check_time`).
- Refuse to give an email → it takes a message → card shows `Callback Needed`.
- "Stop calling me" → card shows `Opted Out`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Call connects but **no card** appears | `CONVERSATION_PROVIDER` must be `elevenlabs`; `docker compose logs -f verification-worker`; confirm the post-call webhook fired, `ELEVENLABS_WEBHOOK_SECRET` matches the portal's signing secret, and you recreated `webhook-ingest` after setting it (`docker compose up -d webhook-ingest`). |
| Tool calls return **401** | The `X-Callwise-Agent-Secret` secret in the portal ≠ `AGENT_TOOLS_SECRET` in `.env`. |
| Agent always **"takes a message"** instead of booking | `CALCOM_API_KEY` / `CALCOM_EVENT_TYPE_ID` wrong, or no open slots — re-run the Part 2.4 pre-flight. |
| Pre-flight returns **`no_slots`** | Open Cal.com Availability and add open hours in the next 7 days (Part 1.1). |
| ElevenLabs **can't reach** the tools / they time out | `BASE_URL` isn't your live tunnel URL, or you didn't restart `webhook-ingest` after changing it. |
| Agent books the **wrong hour** | Check `CALCOM_TIMEZONE` — times are matched in that timezone. |
| Tool call returns **404** (`{"detail":"Not Found"}`) | **Stale image** — the container predates the agent-tools routes. Rebuild `docker compose up -d --build webhook-ingest verification-worker`, then re-check `/openapi.json`. |
| **`cloudflared` not recognized** | That terminal's PATH is stale — run `.\tunnel.ps1` (calls it by full path) or open a new terminal. |
| `curl` → `URL rejected: Port number...` (Windows) | PowerShell mangled the args — use `Invoke-RestMethod` (Part 2.4). |

---

*Production / own-the-stack (LiveKit + Soniox, your own STT and turn-taking): see
[`README.md`](README.md). Same Cal.com booking, same dashboard pipeline — only the conversation
engine changes (`CONVERSATION_PROVIDER=livekit`).*
