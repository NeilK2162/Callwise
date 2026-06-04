export type Direction = "inbound" | "outbound";

export type Outcome =
  | "appointment_booked"
  | "question_answered"
  | "callback_needed"
  | "not_interested"
  | "wrong_number"
  | "wrong_party"
  | "voicemail"
  | "opt_out"
  | "undetermined";

export interface TranscriptTurn {
  role: string;
  text: string;
  ts: number;
}

export interface QueryCard {
  call_session_id: string;
  direction: Direction;
  phone_masked: string;
  customer_name: string | null;
  started_at: string; // ISO
  summary: string | null;
  outcome: Outcome | null;
  confidence: number | null;
  extracted: Record<string, unknown>;
  duration_s: number | null;
  has_recording: boolean;
  transcript?: TranscriptTurn[];
}

export interface Summary {
  calls_today: number;
  booked: number;
  callback_needed: number;
  missed: number;
  avg_duration_s: number;
}

export type FilterKey = "all" | "inbound" | "outbound" | "needs_action";

export const OUTCOME_LABELS: Record<Outcome, string> = {
  appointment_booked: "Appointment Booked",
  question_answered: "Question Answered",
  callback_needed: "Callback Needed",
  not_interested: "Not Interested",
  wrong_number: "Wrong Number",
  wrong_party: "Wrong Party",
  voicemail: "Voicemail",
  opt_out: "Opted Out",
  undetermined: "Undetermined",
};
