import type { QueryCard, Summary } from "@/lib/types";

// Pre-seeded example calls so the feed looks alive on first load, even before a live
// demo call (PRD §0.6). Mirrors the demo seed in the backend (scripts/seed_demo.py).
export const SEED_CARDS: QueryCard[] = [
  {
    call_session_id: "11111111-1111-1111-1111-111111111111",
    direction: "inbound",
    phone_masked: "+91 ····· 4821",
    customer_name: "Priya Sharma",
    started_at: new Date(Date.now() - 14 * 60_000).toISOString(),
    summary:
      "Asked about root canal cost and earliest Saturday slot. Booked for Sat 11 AM. Confirmed via SMS.",
    outcome: "appointment_booked",
    confidence: 0.96,
    extracted: { name: "Priya", service: "root canal", date: "Sat 11AM" },
    duration_s: 132,
    has_recording: true,
    transcript: [
      { role: "agent", text: "Thanks for calling Bright Smile Dental! How can I help?", ts: 0 },
      { role: "customer", text: "Hi, how much is a root canal, and do you have a Saturday slot?", ts: 4 },
      { role: "agent", text: "A root canal starts at ₹6,000. The earliest Saturday is this Sat 11 AM.", ts: 9 },
      { role: "customer", text: "Let's book that.", ts: 14 },
      { role: "agent", text: "Booked for Saturday 11 AM. I've sent a confirmation by SMS.", ts: 17 },
    ],
  },
  {
    call_session_id: "22222222-2222-2222-2222-222222222222",
    direction: "inbound",
    phone_masked: "+91 ····· 5678",
    customer_name: "Rahul Verma",
    started_at: new Date(Date.now() - 38 * 60_000).toISOString(),
    summary:
      "Wanted to reschedule a cleaning but the preferred slot was full. Asked for a callback tomorrow morning.",
    outcome: "callback_needed",
    confidence: 0.81,
    extracted: { name: "Rahul", intent: "reschedule" },
    duration_s: 74,
    has_recording: true,
    transcript: [
      { role: "agent", text: "Bright Smile Dental, how can I help?", ts: 0 },
      { role: "customer", text: "I need to move my cleaning to Thursday.", ts: 3 },
      { role: "agent", text: "Thursday is full. Can someone call you tomorrow morning with options?", ts: 8 },
      { role: "customer", text: "Yes, please.", ts: 12 },
    ],
  },
  {
    call_session_id: "33333333-3333-3333-3333-333333333333",
    direction: "outbound",
    phone_masked: "+91 ····· 2233",
    customer_name: "Aisha Khan",
    started_at: new Date(Date.now() - 65 * 60_000).toISOString(),
    summary: "Appointment reminder for Friday 4 PM. Confirmed attendance.",
    outcome: "question_answered",
    confidence: 0.9,
    extracted: { name: "Aisha", confirmed: true },
    duration_s: 41,
    has_recording: true,
    transcript: [
      { role: "agent", text: "Hi Aisha, a reminder for your Friday 4 PM appointment.", ts: 0 },
      { role: "customer", text: "Thanks, I'll be there.", ts: 4 },
    ],
  },
  {
    call_session_id: "44444444-4444-4444-4444-444444444444",
    direction: "outbound",
    phone_masked: "+91 ····· 7781",
    customer_name: "Vikram Rao",
    started_at: new Date(Date.now() - 92 * 60_000).toISOString(),
    summary: "Reminder call. Not interested in the whitening upsell; appointment still on.",
    outcome: "not_interested",
    confidence: 0.74,
    extracted: { name: "Vikram", upsell: "whitening", interested: false },
    duration_s: 53,
    has_recording: true,
  },
  {
    call_session_id: "55555555-5555-5555-5555-555555555555",
    direction: "inbound",
    phone_masked: "+91 ····· 9012",
    customer_name: "Neha Gupta",
    started_at: new Date(Date.now() - 121 * 60_000).toISOString(),
    summary: "New patient enquiry about braces consultation pricing. Booked a consult for Monday.",
    outcome: "appointment_booked",
    confidence: 0.94,
    extracted: { name: "Neha", service: "braces consult", date: "Mon 5PM" },
    duration_s: 167,
    has_recording: true,
  },
];

export const SEED_SUMMARY: Summary = {
  calls_today: 47,
  booked: 31,
  callback_needed: 8,
  missed: 0,
  avg_duration_s: 112,
};
