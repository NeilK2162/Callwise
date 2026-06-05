export const DEMO_NUMBER = process.env.NEXT_PUBLIC_DEMO_NUMBER ?? "+1 (555) 010-2024";

export function demoTelHref(number = DEMO_NUMBER): string {
  return `tel:${number.replace(/[^+\d]/g, "")}`;
}
