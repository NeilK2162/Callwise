# Agent conversation design & edge-case matrix

The voice agent (`backend/src/callwise/providers/conversation/livekit_agent.py`) is a real
receptionist, not a happy-path demo. Every situation has a defined, kind resolution that maps
to a dashboard outcome — the front desk always knows what happened and what to do next.

## Design principles

- **Short turns, one question at a time.** It's a phone call, not a form.
- **Confirm before acting.** Read the email and name back before booking (STT mangles emails).
- **Never dead-end.** If it can't finish a booking, it *takes a message* — the caller is never
  stranded and the desk always gets a follow-up task.
- **The agent's signals are authoritative.** What the agent actually did (booked / messaged /
  opted-out) overrides the LLM's transcript read when tagging the call.
- **Privacy first.** Never disclose an existing patient's details to an unverified caller.

## Tools the agent can call

| Tool | When | Effect |
|---|---|---|
| `check_availability(preference?)` | caller wants to book / asks what's open | reads live Cal.com slots; signals `NO_SLOTS` if empty |
| `book_appointment(name, email, slot_iso)` | a slot is chosen + read back | live Cal.com booking; mutating → interruptions disabled |
| `take_message(name, reason, details?, callback_window?)` | can't book live | structured callback for the desk |
| `mark_do_not_contact()` | caller asks to stop | permanent suppression |

## Edge-case matrix

| Situation | Agent behavior | Dashboard outcome |
|---|---|---|
| **Happy path** — slot chosen, booked | read-back → `book_appointment` → confirm day/time + "confirmation sent" | ✅ **Appointment Booked** (+ `booking_uid`, `booked_for`) |
| **Slot taken between read & book** (race) | `BookingUnavailable` → agent re-offers fresh times, doesn't claim success | Booked (on the retry) |
| **No times work / nothing available** | apologize → `take_message(reason=no_suitable_time, callback_window)` | ↩ **Callback Needed** (`callback_reason=no_suitable_time`) |
| **Caller won't / can't give email** | `take_message(reason=book_no_email)` — desk confirms to their phone | ↩ Callback Needed |
| **Reschedule / cancel existing** | can't mutate existing bookings → `take_message(reason=reschedule\|cancel, details)` | ↩ Callback Needed |
| **Wants a human / front desk** | `take_message(reason=wants_human)` (warm transfer is a future option) | ↩ Callback Needed |
| **Question it can't answer** (specific pricing, insurance, clinical) | answer if truly known, else `take_message(reason=question, details=<the question>)` | ↩ Callback Needed / 💬 Question Answered |
| **Booking system down** (5xx/network) | falls back to a message so the caller isn't stranded | ↩ Callback Needed (`booking_failed`) |
| **"Stop calling me" / do-not-call** | `mark_do_not_contact` → confirm → end | ⛔ **Opted Out** → suppressed across all campaigns |
| **Wrong person / can't verify identity** | never discloses details → offers a general message → ends | ❓ Wrong Party |
| **Silence / unintelligible after one re-prompt** | offers to call back, ends politely | Undetermined → reconciler/desk review |
| **Answering machine (outbound)** | telephony AMD tags it before the agent engages | 📩 Voicemail (retry per policy) |
| **No-answer / busy (outbound)** | provider status callback | retried with backoff, then `max_attempts` |

## How outcomes reach the dashboard

On hangup the agent POSTs `{transcript, booking, message, opted_out, from_number}` to
`/api/v2/webhooks/livekit`. The verification worker:

1. Creates the inbound `call_session` (caller-initiated calls have no pre-created session).
2. Runs **one** LLM call for the summary + extraction (cost-controlled, PRD §19).
3. **Overrides** the outcome with the agent's authoritative signal (opt-out → booked →
   message), extracting `booking_uid` / `callback_reason` / `details` onto the card.
4. Opt-out also writes the cross-campaign suppression list.

The result is a query card whose tag and "next action" are always trustworthy — a booked
appointment, a callback with the exact reason, or a clean opt-out.
