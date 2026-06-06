// Estimated value per booked appointment — the clinic sets this to their average ticket.
// It powers the "booked revenue" story (PRD §0.3 ROI math). Configurable, honest estimate.
const APPT_VALUE = Number(process.env.NEXT_PUBLIC_APPT_VALUE ?? 2000);
const CURRENCY = process.env.NEXT_PUBLIC_CURRENCY ?? "₹";

export function apptValue(): number {
  return APPT_VALUE;
}

export function fmtMoney(n: number): string {
  return CURRENCY + Math.round(n).toLocaleString("en-IN");
}
