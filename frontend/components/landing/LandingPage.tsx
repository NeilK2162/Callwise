"use client";

import Link from "next/link";
import { Phone, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { FinalWave, StaticWave, Waveform } from "@/components/Waveform";
import { ScrollReveal } from "@/components/ScrollReveal";
import { DEMO_NUMBER, demoTelHref } from "@/lib/constants";

function CheckIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export function LandingPage() {
  return (
    <>
      <nav className="landing-nav">
        <div className="landing-nav-in">
          <Link className="landing-brand" href="/">
            <BrandMark />
            <b>Callwise</b>
          </Link>
          <div className="landing-nav-links">
            <a className="lk" href="#how">
              How it works
            </a>
            <a className="lk" href="#pricing">
              Pricing
            </a>
            <Link className="lk" href="/dashboard">
              Dashboard
            </Link>
            <a className="btn btn-primary" href={demoTelHref()}>
              <Phone size={16} strokeWidth={2.2} />
              Call the agent
            </a>
          </div>
        </div>
      </nav>

      <header className="hero" id="top">
        <div className="grain" />
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <span className="pill">
              <span className="dot" />
              <span className="eyebrow">AI voice agent · inbound + outbound</span>
            </span>
            <h1 className="hero-h">
              Never miss a
              <br />
              customer call <em>again.</em>
            </h1>
            <p className="hero-sub">
              Callwise answers every inbound call in a natural voice, makes your outbound
              follow-ups, and turns each conversation into a clean, tagged record — 24/7, even at
              2&nbsp;AM.
            </p>
            <div className="hero-cta">
              <a className="btn btn-primary btn-lg" href={demoTelHref()}>
                <Phone size={18} strokeWidth={2.2} />
                Call the agent now
              </a>
              <Link className="btn btn-ghost btn-lg" href="/dashboard">
                See the dashboard
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              </Link>
            </div>
            <div className="hero-num">
              <span className="mono">{DEMO_NUMBER}</span> · experience it in 20 seconds
            </div>
          </div>

          <div className="callpanel">
            <div className="cp-top">
              <div className="cp-id">
                <div className="cp-av">
                  <Phone size={20} strokeWidth={2} />
                </div>
                <div>
                  <b>Priya Sharma</b>
                  <span>+91 ····· 4821 · 02:14 AM</span>
                </div>
              </div>
              <span className="cp-live">
                <i /> Live
              </span>
            </div>
            <Waveform className="wave cp-wave" bars={44} height={54} />
            <div className="cp-trans">
              <div className="bub agent">
                A root canal starts at $900. Earliest Saturday is 11&nbsp;AM.
              </div>
              <div className="bub cust">Let&apos;s book that.</div>
              <div className="bub agent">
                Booked for Saturday 11&nbsp;AM — confirmation sent by SMS.
              </div>
            </div>
            <div className="cp-foot">
              <span
                className="cp-live"
                style={{
                  color: "var(--warm-soft)",
                  background: "rgba(232,130,90,.1)",
                  borderColor: "rgba(232,130,90,.3)",
                }}
              >
                <i style={{ background: "var(--warm)" }} /> Transcribing · auto-tagging
              </span>
              <span className="cp-meta">call_11a2</span>
            </div>
          </div>
        </div>
      </header>

      <section className="trust">
        <div className="wrap">
          <div className="t">
            <b>0</b> missed calls
          </div>
          <div className="t">
            <b>24/7</b> always answering
          </div>
          <div className="t">
            <b>~12s</b> avg pickup → booked
          </div>
          <div className="t">
            <b>96%</b> auto-tag confidence
          </div>
          <div className="t">
            <b>1</b> dashboard for everything
          </div>
        </div>
      </section>

      <section className="band roi" id="roi">
        <div className="wrap roi-grid">
          <ScrollReveal>
            <span className="eyebrow" style={{ color: "var(--warm-soft)" }}>
              The math
            </span>
            <h2>
              A missed call is <em>lost revenue.</em>
            </h2>
            <p>
              A clinic missing <b>10 calls a week</b> at an average patient value of{" "}
              <b>$300</b> bleeds roughly <b>$12,000 every month</b> to voicemail and busy
              signals. Callwise answers every one — and books the appointment or flags the
              callback.
            </p>
            <p style={{ marginTop: 14 }}>
              <b>It pays for itself in the first week.</b>
            </p>
          </ScrollReveal>
          <ScrollReveal delay={0.08}>
            <div className="meter">
              <div className="row">
                <span className="k">Missed calls / week</span>
                <span className="v bad">10</span>
              </div>
              <div className="row">
                <span className="k">Avg. patient value</span>
                <span className="v">$300</span>
              </div>
              <div className="row">
                <span className="k">Lost revenue / month</span>
                <span className="v bad">$12,000</span>
              </div>
              <div className="row">
                <span className="k">Recovered with Callwise</span>
                <span className="v good" style={{ whiteSpace: "nowrap" }}>
                  +$12,000
                </span>
              </div>
              <div style={{ marginTop: 18 }}>
                <div className="big" style={{ color: "var(--warm-soft)" }}>
                  $0
                </div>
                <div className="cap">missed calls, going forward</div>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </section>

      <section className="band" id="how">
        <div className="wrap">
          <ScrollReveal className="rv sec-head">
            <div className="l">
              <span className="eyebrow">How it works</span>
              <h2 className="sh">
                One agent. Three jobs.
                <br />
                Zero dropped calls.
              </h2>
            </div>
            <p>
              From the first ring to the tagged record in your dashboard, every step runs on its
              own — no staff, no scripts to read, no after-hours gap.
            </p>
          </ScrollReveal>
          <div className="steps">
            {[
              {
                n: "01",
                icon: PhoneIncoming,
                title: "It answers",
                body: "Inbound calls are picked up instantly in a natural voice — hours, booking, FAQ, intake. No missed calls, ever.",
                seed: 0,
              },
              {
                n: "02",
                icon: PhoneOutgoing,
                title: "It follows up",
                body: "Outbound reminders, lead qualification and feedback calls run automatically — and record every outcome.",
                seed: 1,
              },
              {
                n: "03",
                icon: null,
                title: "You see everything",
                body: "Every call becomes a tagged, searchable card — summary, transcript, recording and extracted details.",
                seed: 2,
              },
            ].map((s, idx) => (
              <ScrollReveal key={s.n} className="rv step" delay={(idx % 3) * 0.08}>
                <div className="n">{s.n}</div>
                <div className="ic">
                  {s.icon ? (
                    <s.icon size={22} strokeWidth={2} />
                  ) : (
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="7" height="9" />
                      <rect x="14" y="3" width="7" height="5" />
                      <rect x="14" y="12" width="7" height="9" />
                      <rect x="3" y="16" width="7" height="5" />
                    </svg>
                  )}
                </div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                <StaticWave bars={26} className="wave ml" seed={s.seed} />
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <section className="band example" id="example">
        <div className="wrap ex-grid">
          <ScrollReveal>
            <span className="eyebrow">The record</span>
            <h2 className="sh">
              Every call,
              <br />
              one clean record.
            </h2>
            <p style={{ marginTop: 16, color: "var(--ink-3)", fontSize: 17, maxWidth: 420 }}>
              No note-taking. The agent transcribes, summarises, tags the outcome and pulls out the
              details that matter — booked, callback, or question answered.
            </p>
            <Link className="btn btn-primary btn-lg" style={{ marginTop: 26 }} href="/dashboard">
              Open the full dashboard
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </Link>
          </ScrollReveal>
          <ScrollReveal delay={0.08}>
            <div className="qcard-static">
              <div className="qc-top">
                <span className="qc-dir">
                  <PhoneIncoming size={14} strokeWidth={2.2} />
                  Inbound
                </span>
                <span>· +91 ····· 4821 · Today 02:14 AM</span>
              </div>
              <div className="qc-name-row">
                <b>Priya Sharma</b>
                <span className="badge badge-booked">
                  <span className="dt" /> Appointment Booked
                </span>
              </div>
              <p className="qc-sum">
                Asked about root canal cost and earliest Saturday slot. Booked for Sat 11&nbsp;AM.
                Confirmed via SMS.
              </p>
              <div className="qc-tags">
                <span className="tag">name = Priya</span>
                <span className="tag">service = root canal</span>
                <span className="tag">date = Sat 11AM</span>
              </div>
              <div className="qc-foot">
                <span>▶ Recording</span>
                <span>≡ Transcript</span>
                <span className="sp">confidence 96%</span>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </section>

      <section className="band" id="pricing">
        <div className="wrap">
          <ScrollReveal
            className="rv sec-head"
            delay={0}
          >
            <div
              className="l"
              style={{ textAlign: "center", maxWidth: "100%", margin: "0 auto 72px" }}
            >
              <span className="eyebrow">Pricing</span>
              <h2 className="sh">
                Simple pricing.
                <br />
                It pays for itself.
              </h2>
            </div>
          </ScrollReveal>
          <div className="price-grid">
            {[
              {
                name: "Starter",
                price: "$199",
                per: "/mo",
                feat: false,
                items: ["1 phone number", "Up to 500 calls / mo", "Dashboard + transcripts"],
                cta: "Start free trial",
              },
              {
                name: "Growth",
                price: "$499",
                per: "/mo",
                feat: true,
                items: ["3 phone numbers", "Up to 2,500 calls / mo", "Outbound campaigns", "Priority support"],
                cta: "Start free trial",
              },
              {
                name: "Scale",
                price: "Custom",
                per: "",
                feat: false,
                items: ["Number pool", "Unlimited calls", "Custom integrations", "SLA + onboarding"],
                cta: "Talk to sales",
              },
            ].map((p, idx) => (
              <ScrollReveal key={p.name} className={`rv plan${p.feat ? " feat" : ""}`} delay={(idx % 3) * 0.08}>
                {p.feat && <span className="ribbon">Popular</span>}
                <div className="pn">{p.name}</div>
                <div className="pp">
                  {p.price}
                  {p.per && <span className="pper">{p.per}</span>}
                </div>
                <ul>
                  {p.items.map((item) => (
                    <li key={item}>
                      <CheckIcon /> {item}
                    </li>
                  ))}
                </ul>
                <a className="pbtn" href={demoTelHref()}>
                  {p.cta}
                </a>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <section className="band final" id="final">
        <div className="wrap">
          <FinalWave />
          <h2>
            Hear it for <em>yourself.</em>
          </h2>
          <p>Inbound, outbound, every conversation in one place. Call the live agent now.</p>
          <div className="hero-cta" style={{ justifyContent: "center", marginTop: 30 }}>
            <a className="btn btn-primary btn-lg" href={demoTelHref()}>
              <Phone size={18} strokeWidth={2.2} />
              Call {DEMO_NUMBER}
            </a>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="wrap">
          <Link className="landing-brand" href="/">
            <BrandMark />
            <b style={{ fontSize: 16 }}>Callwise</b>
          </Link>
          <span>© {new Date().getFullYear()} Callwise · AI voice agents for clinics, home services &amp; agencies</span>
        </div>
      </footer>
    </>
  );
}
