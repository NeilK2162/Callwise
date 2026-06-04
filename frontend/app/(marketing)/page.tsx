import Link from "next/link";
import { Phone, ArrowRight, Check, PhoneIncoming, PhoneOutgoing, LayoutDashboard } from "lucide-react";

const DEMO_NUMBER = "+1 (555) 010-2024"; // replace with your live agent number

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-white">
      {/* Nav */}
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5">
        <span className="text-xl font-bold tracking-tight text-brand-600">Callwise</span>
        <Link href="/dashboard" className="text-sm font-medium text-ink-700 hover:text-brand-600">
          View the dashboard →
        </Link>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 pb-12 pt-10 text-center">
        <p className="mb-3 inline-block rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
          AI voice agent · inbound + outbound
        </p>
        <h1 className="mx-auto max-w-3xl text-4xl font-bold leading-tight tracking-tight text-ink-900 sm:text-5xl">
          Never miss a customer call again.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-ink-700">
          Callwise answers every inbound call with a natural AI voice, makes your outbound
          follow-ups, and turns every conversation into a clean, tagged query in one dashboard —
          24/7, even at 2 AM.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <a
            href={`tel:${DEMO_NUMBER.replace(/[^+\d]/g, "")}`}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-3 text-base font-semibold text-white shadow-sm transition hover:bg-brand-600"
          >
            <Phone className="h-5 w-5" /> Call the agent now
          </a>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-5 py-3 text-base font-semibold text-ink-700 transition hover:bg-slate-50"
          >
            See the dashboard <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <p className="mt-3 text-sm text-ink-500">{DEMO_NUMBER} · experience it in 20 seconds</p>
      </section>

      {/* ROI math */}
      <section className="bg-slate-50 py-14">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <h2 className="text-2xl font-bold text-ink-900">Missed call = lost revenue.</h2>
          <p className="mt-3 text-ink-700">
            A clinic missing 10 calls a week at an average patient value of ₹2,000 is losing
            <span className="font-semibold text-ink-900"> ~₹80,000 a month</span> to voicemail and
            busy signals. Callwise answers every one of them and books the appointment or flags the
            callback. <span className="font-semibold text-ink-900">It pays for itself in the first week.</span>
          </p>
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="mb-10 text-center text-2xl font-bold text-ink-900">How it works</h2>
        <div className="grid gap-6 sm:grid-cols-3">
          {[
            {
              icon: PhoneIncoming,
              title: "It answers",
              body: "Inbound calls are picked up instantly in a natural voice — hours, booking, FAQ, intake. No missed calls, ever.",
            },
            {
              icon: PhoneOutgoing,
              title: "It follows up",
              body: "Outbound reminders, lead qualification, and feedback calls run automatically and record the outcome.",
            },
            {
              icon: LayoutDashboard,
              title: "You see everything",
              body: "Every call becomes a tagged, searchable query card with the summary, transcript, recording, and extracted details.",
            },
          ].map((s) => (
            <div key={s.title} className="rounded-2xl border border-slate-200 p-6 shadow-sm">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <s.icon className="h-5 w-5" />
              </div>
              <h3 className="font-semibold text-ink-900">{s.title}</h3>
              <p className="mt-1 text-sm text-ink-700">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Example query card */}
      <section className="bg-slate-50 py-16">
        <div className="mx-auto max-w-2xl px-4">
          <h2 className="mb-6 text-center text-2xl font-bold text-ink-900">
            Every call, one clean record
          </h2>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-xs text-ink-500">
              <PhoneIncoming className="h-3.5 w-3.5" />
              <span className="font-medium uppercase tracking-wide">inbound</span>
              <span>· +91 ····· 4821 · Today 02:14 AM</span>
            </div>
            <div className="mt-2 flex items-baseline justify-between">
              <div className="font-semibold text-ink-900">Priya Sharma</div>
              <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                ✅ Appointment Booked
              </span>
            </div>
            <p className="mt-1 text-sm text-ink-700">
              Asked about root canal cost and earliest Saturday slot. Booked for Sat 11 AM.
              Confirmed via SMS.
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-ink-500">
              <span className="rounded bg-slate-100 px-1.5 py-0.5">name=Priya</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5">service=root canal</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5">date=Sat 11AM</span>
            </div>
          </div>
          <div className="mt-6 text-center">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 text-sm font-semibold text-brand-600 hover:text-brand-700"
            >
              Open the full dashboard <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="mb-10 text-center text-2xl font-bold text-ink-900">Simple pricing</h2>
        <div className="grid gap-6 sm:grid-cols-3">
          {[
            { name: "Starter", price: "₹9,999/mo", features: ["1 number", "Up to 500 calls/mo", "Dashboard + transcripts"] },
            { name: "Growth", price: "₹24,999/mo", features: ["3 numbers", "Up to 2,500 calls/mo", "Outbound campaigns", "Priority support"], featured: true },
            { name: "Scale", price: "Custom", features: ["Number pool", "Unlimited calls", "Custom integrations", "SLA + onboarding"] },
          ].map((p) => (
            <div
              key={p.name}
              className={`rounded-2xl border p-6 shadow-sm ${
                p.featured ? "border-brand-500 ring-1 ring-brand-500" : "border-slate-200"
              }`}
            >
              <h3 className="font-semibold text-ink-900">{p.name}</h3>
              <div className="mt-1 text-2xl font-bold text-ink-900">{p.price}</div>
              <ul className="mt-4 space-y-2 text-sm text-ink-700">
                {p.features.map((f) => (
                  <li key={f} className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-600" /> {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="bg-ink-900 py-16 text-center text-white">
        <div className="mx-auto max-w-2xl px-4">
          <h2 className="text-3xl font-bold">Hear it for yourself.</h2>
          <p className="mt-3 text-slate-300">
            Inbound, outbound, every conversation in one place. Call the live agent now.
          </p>
          <a
            href={`tel:${DEMO_NUMBER.replace(/[^+\d]/g, "")}`}
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-brand-500 px-6 py-3 text-base font-semibold text-white transition hover:bg-brand-600"
          >
            <Phone className="h-5 w-5" /> Call {DEMO_NUMBER}
          </a>
        </div>
      </section>

      <footer className="mx-auto max-w-6xl px-4 py-8 text-center text-sm text-ink-500">
        © {new Date().getFullYear()} Callwise · AI voice agents for clinics, home services & agencies
      </footer>
    </main>
  );
}
