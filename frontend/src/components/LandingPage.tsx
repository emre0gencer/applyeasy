import { useEffect, useRef, useState } from "react";
import { uploadText } from "../api/client";
import { ResumeGallery } from "./ResumeGallery";

interface Props {
  onSubmit: (sessionId: string, rawText: string) => void;
  initialText?: string;
}

const SLOGANS = [
  "ATS-OPTIMIZED",
  "KEYWORD-ACCURATE",
  "ZERO HALLUCINATIONS",
  "30-SECOND RESULTS",
  "ONE PAGE BY DEFAULT",
  "GROUNDED IN YOUR EXPERIENCE",
  "NO ACCOUNT REQUIRED",
  "TAILORED TO THE ROLE",
  "BUILT DIFFERENTLY",
  "YOUR WORDS, BETTER PLACED",
];

export function LandingPage({ onSubmit, initialText = "" }: Props) {
  const [scrolled, setScrolled] = useState(false);
  const [text, setText] = useState(initialText);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [ctaHovered, setCtaHovered] = useState(false);
  const [bottomCtaHovered, setBottomCtaHovered] = useState(false);
  const [navLinkHovered, setNavLinkHovered] = useState(false);
  const [textareaFocused, setTextareaFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  async function handleSubmit() {
    if (!text.trim()) {
      setError("Paste your background to continue.");
      textareaRef.current?.focus();
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await uploadText(text);
      onSubmit(res.session_id, text);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function scrollToForm() {
    const startY = window.scrollY;
    if (startY === 0) {
      textareaRef.current?.focus();
      return;
    }
    const duration = Math.min(300 + startY * 0.35, 1100); // proportional, max 1.1s
    const startTime = performance.now();
    function easeOutCubic(t: number) { return 1 - Math.pow(1 - t, 3); }
    function step(now: number) {
      const t = easeOutCubic(Math.min((now - startTime) / duration, 1));
      window.scrollTo(0, startY * (1 - t));
      if (t < 1) requestAnimationFrame(step);
      else textareaRef.current?.focus();
    }
    requestAnimationFrame(step);
  }

  const marqueeItems = [...SLOGANS, ...SLOGANS];

  return (
    <div style={s.root}>
      <style>{`
        @keyframes marquee {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
      `}</style>

      {/* ── Nav ── */}
      <nav
        style={{
          ...s.nav,
          background: scrolled ? "rgba(2,8,20,0.98)" : "rgba(2,8,20,0.55)",
        }}
      >
        <span style={s.navWordmark}>
          <span style={{ color: "#f1f5f9", fontWeight: 900 }}>Apply</span>
          <span style={{ color: "#3b82f6", fontWeight: 900 }}>Easy</span>
        </span>
        <div style={s.navRight}>
          <a
            href="#how-it-works"
            style={{ ...s.navLink, color: navLinkHovered ? "#cbd5e1" : "#64748b" }}
            onMouseEnter={() => setNavLinkHovered(true)}
            onMouseLeave={() => setNavLinkHovered(false)}
          >
            How it works
          </a>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section style={s.hero}>
        <div style={s.heroAtmosphere} />

        {/* ── Marquee — floats in the upper hero area, not connected to nav ── */}
        <div style={s.marqueeOuter}>
          <div style={s.marqueeTrack}>
            {marqueeItems.map((slogan, i) => (
              <span key={i} style={s.marqueeItem}>
                <span style={s.marqueeDiamond}>◆</span>
                {slogan}
              </span>
            ))}
          </div>
        </div>
        <div style={s.heroInner}>

          {/* Left: copy */}
          <div style={s.heroLeft}>
            <div style={s.eyebrow}>
              <span style={s.eyebrowBar} />
              <span style={s.eyebrowText}>AI-POWERED RESUME TAILORING</span>
            </div>

            <h1 style={s.headline}>
              Your resume,<br />
              rewritten for<br />
              <span style={s.headlineAccent}>every role.</span>
            </h1>

            <div style={s.metaRow}>
              {["ATS-safe PDF", "One page by default", "~30 seconds"].map((item) => (
                <span key={item} style={s.metaPill}>
                  <span style={s.metaCheck}>✓</span>
                  {item}
                </span>
              ))}
            </div>

            <div style={s.disclaimer}>
              <span style={s.disclaimerIcon}>⚠</span>
              <p style={s.disclaimerText}>
                <strong>Use at your own risk.</strong>{" "}
                This application tailors your professional profile based on the job posting and
                information you provide. It doesn't validate accuracy or suitability — responsibility
                for honest representation is entirely yours.
              </p>
            </div>
          </div>

          {/* Right: form card */}
          <div style={s.formCard}>
            <div style={s.formHeader}>
              <div style={s.formTitle}>Your professional background</div>
              <div style={s.formSubtitle}>
                Resume, LinkedIn export, or any plain text. No formatting required.
              </div>
            </div>

            <textarea
              ref={textareaRef}
              style={{
                ...s.textarea,
                borderColor: textareaFocused
                  ? "rgba(59,130,246,0.6)"
                  : error
                  ? "rgba(239,68,68,0.6)"
                  : "rgba(255,255,255,0.12)",
                boxShadow: textareaFocused
                  ? "0 0 0 3px rgba(59,130,246,0.12)"
                  : "none",
              }}
              value={text}
              onChange={(e) => { setText(e.target.value); if (error) setError(""); }}
              onFocus={() => setTextareaFocused(true)}
              onBlur={() => setTextareaFocused(false)}
              placeholder={
                "Jane Smith\njane@email.com | linkedin.com/in/janesmith\n\nSoftware Engineer at Acme Corp (Jan 2022 – Present)\n- Built Kafka pipeline processing 2M events/day\n- Led migration from monolith to microservices\n\nB.S. Computer Science, UC Berkeley, 2020\nGPA: 3.8 | Dean's List\n\nSkills: Python, FastAPI, React, PostgreSQL, Docker, Kubernetes"
              }
              rows={13}
            />

            {error && <div style={s.errorMsg}>{error}</div>}

            <button
              style={{
                ...s.cta,
                background: loading ? "#1e3a8a" : "#2563eb",
                boxShadow:
                  ctaHovered && !loading
                    ? "4px 4px 0 rgba(255,255,255,0.18)"
                    : "3px 3px 0 rgba(0,0,0,0.45)",
                transform: ctaHovered && !loading ? "translate(-1px,-1px)" : "none",
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.8 : 1,
              }}
              onClick={handleSubmit}
              disabled={loading}
              onMouseEnter={() => setCtaHovered(true)}
              onMouseLeave={() => setCtaHovered(false)}
            >
              {loading ? "Processing…" : "Tailor my resume →"}
            </button>

            <div style={s.formFootnote}>
              No account required · Data never stored beyond your session
            </div>
          </div>
        </div>
      </section>

      {/* ── Resume Gallery ── */}
      <ResumeGallery />

      {/* ── How It Works ── */}
      <section id="how-it-works" style={s.howSection}>
        <div style={s.sectionInner}>
          <div style={s.sectionLabel}>Process</div>
          <h2 style={s.sectionHeading}>
            Three steps.<br />One tailored PDF.
          </h2>

          <div style={s.stepsGrid}>
            {[
              {
                n: "01",
                title: "Paste your background",
                body: "Drop in your full work history, skills, and education. Any plain text works — resume, LinkedIn export, or freeform notes.",
              },
              {
                n: "02",
                title: "Add the job description",
                body: "Paste the full job posting. ApplyEasy extracts requirements, importance-ranked keywords, and what the role actually demands.",
              },
              {
                n: "03",
                title: "Download tailored documents",
                body: "Get a one-page ATS-safe PDF with reordered, keyword-rich bullets — every claim traceable to your real experience.",
              },
            ].map((step) => (
              <div key={step.n} style={s.stepCard}>
                <div style={s.stepNumGhost}>{step.n}</div>
                <div style={s.stepNumLabel}>{step.n}</div>
                <div style={s.stepTitle}>{step.title}</div>
                <div style={s.stepBody}>{step.body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Feature Callouts ── */}
      <section style={s.featureSection}>
        <div style={s.sectionInner}>
          <div style={s.sectionLabel}>Engineering</div>
          <h2 style={s.sectionHeading}>
            Built differently from<br />other AI resume tools.
          </h2>

          <div style={s.featureGrid}>
            {[
              {
                tag: "STRUCTURE",
                title: "ATS-safe by design",
                body: "The output PDF uses a clean single-column layout with standard section headings that applicant tracking systems expect. No tables, no columns, no parsing failures.",
              },
              {
                tag: "INTEGRITY",
                title: "Zero hallucination guarantee",
                body: "Every rewritten bullet is grounded in your original text. A validation layer flags any metric, name, or claim that wasn't present in your source material.",
              },
              {
                tag: "PRECISION",
                title: "Keyword-targeted, not stuffed",
                body: "Keywords are ranked by importance from the job description and woven in only where technically accurate. The engine caps integrations per bullet so copy reads naturally.",
              },
            ].map((f) => (
              <div key={f.title} style={s.featureCard}>
                <div style={s.featureTag}>{f.tag}</div>
                <div style={s.featureTitle}>{f.title}</div>
                <div style={s.featureBody}>{f.body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Bottom CTA ── */}
      <section style={s.bottomCta}>
        <div style={s.bottomCtaInner}>
          <div style={s.sectionLabel}>Get started</div>
          <h2 style={s.bottomCtaHeading}>
            Ready for your<br />next application?
          </h2>
          <p style={s.bottomCtaSubhead}>
            No account. No credit card. Paste your background and go.
          </p>
          <button
            style={{
              ...s.ctaBottom,
              background: bottomCtaHovered ? "#1d4ed8" : "#2563eb",
              boxShadow: bottomCtaHovered
                ? "5px 5px 0 rgba(255,255,255,0.18)"
                : "4px 4px 0 rgba(0,0,0,0.5)",
              transform: bottomCtaHovered ? "translate(-1px,-1px)" : "none",
            }}
            onClick={scrollToForm}
            onMouseEnter={() => setBottomCtaHovered(true)}
            onMouseLeave={() => setBottomCtaHovered(false)}
          >
            Start tailoring →
          </button>
        </div>
      </section>

      {/* ── Trust Bar ── */}
      <div style={s.trustBar}>
        ApplyEasy never stores your resume beyond your session. All documents are
        generated in memory and available only during your active session.
      </div>

      {/* ── Footer ── */}
      <footer style={s.footer}>
        <span style={s.footerWordmark}>ApplyEasy</span>
        <span style={s.footerMeta}>© {new Date().getFullYear()}</span>
      </footer>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {

  root: {
    fontFamily: "'Manrope', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    color: "#f1f5f9",
    background: "transparent",
    overflowX: "hidden",
  },

  /* ── Nav ── */
  nav: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 100,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "0 44px",
    height: 64,
    backdropFilter: "blur(20px)",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    transition: "background 0.25s",
  },
  navWordmark: {
    fontSize: 20,
    letterSpacing: "-0.04em",
    display: "flex",
    alignItems: "baseline",
    userSelect: "none" as const,
    cursor: "default",
  },
  navRight: {
    display: "flex",
    alignItems: "center",
    gap: 24,
  },
  navLink: {
    fontSize: 13,
    fontWeight: 500,
    textDecoration: "none",
    letterSpacing: "0.01em",
    transition: "color 0.15s",
  },

  /* ── Hero ── */
  hero: {
    position: "relative",
    minHeight: "100vh",
    paddingTop: 64,
    display: "flex",
    alignItems: "center",
    background: "transparent",
    overflow: "hidden",
  },
  heroAtmosphere: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: [
      "radial-gradient(ellipse at 70% 55%, rgba(37,99,235,0.08) 0%, transparent 50%)",
      "radial-gradient(ellipse at 15% 30%, rgba(56,189,248,0.04) 0%, transparent 42%)",
    ].join(", "),
    pointerEvents: "none",
  },
  heroInner: {
    position: "relative",
    zIndex: 1,
    maxWidth: 1320,
    margin: "0 auto",
    padding: "72px 60px 88px",
    display: "grid",
    gridTemplateColumns: "1.2fr 1fr",
    gap: "80px",
    alignItems: "center",
    width: "100%",
    boxSizing: "border-box" as React.CSSProperties["boxSizing"],
  },
  heroLeft: {
    display: "flex",
    flexDirection: "column" as React.CSSProperties["flexDirection"],
  },

  /* Eyebrow */
  eyebrow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 24,
  },
  eyebrowBar: {
    width: 24,
    height: 2,
    background: "#3b82f6",
    flexShrink: 0,
  },
  eyebrowText: {
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: "0.14em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#3b82f6",
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  },

  /* Headline */
  headline: {
    fontSize: 96,
    fontWeight: 900,
    lineHeight: 0.97,
    letterSpacing: "-0.05em",
    color: "#f1f5f9",
    margin: "0 0 32px 0",
  },
  headlineAccent: {
    color: "#3b82f6",
    display: "block",
  },

  metaRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap" as React.CSSProperties["flexWrap"],
    marginBottom: 30,
  },
  metaPill: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 13,
    fontWeight: 600,
    color: "#94a3b8",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.09)",
    padding: "7px 15px",
    borderRadius: 100,
    letterSpacing: "0.01em",
  },
  metaCheck: {
    color: "#4ade80",
    fontWeight: 700,
    fontSize: 12,
  },

  /* Disclaimer */
  disclaimer: {
    display: "flex",
    alignItems: "flex-start",
    gap: 8,
    paddingLeft: 12,
    borderLeft: "2px solid rgba(255,255,255,0.07)",
  },
  disclaimerIcon: {
    fontSize: 11,
    color: "#475569",
    flexShrink: 0,
    marginTop: 1,
  },
  disclaimerText: {
    fontSize: 11,
    color: "#475569",
    lineHeight: 1.65,
    margin: 0,
  },

  /* Form card */
  formCard: {
    position: "relative",
    background: "rgba(4,12,30,0.88)",
    backdropFilter: "blur(20px)",
    borderRadius: 14,
    padding: "36px",
    border: "1.5px solid rgba(255,255,255,0.12)",
    boxShadow: [
      "6px 6px 0 rgba(0,0,0,0.4)",
      "0 24px 56px -12px rgba(0,0,0,0.6)",
    ].join(", "),
  },
  formHeader: {
    marginBottom: 20,
  },
  formTitle: {
    fontSize: 15,
    fontWeight: 800,
    color: "#e2e8f0",
    marginBottom: 5,
    letterSpacing: "-0.01em",
  },
  formSubtitle: {
    fontSize: 13,
    color: "#64748b",
    lineHeight: 1.55,
  },
  textarea: {
    display: "block",
    width: "100%",
    padding: "14px 16px",
    border: "1px solid",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    resize: "vertical" as React.CSSProperties["resize"],
    boxSizing: "border-box" as React.CSSProperties["boxSizing"],
    marginBottom: 14,
    lineHeight: 1.65,
    color: "#cbd5e1",
    background: "rgba(1,6,18,0.7)",
    outline: "none",
    transition: "border-color 0.15s, box-shadow 0.15s",
    minHeight: 260,
  },
  errorMsg: {
    fontSize: 13,
    color: "#fca5a5",
    marginBottom: 10,
    marginTop: -6,
  },
  cta: {
    display: "block",
    width: "100%",
    padding: "15px 24px",
    border: "2px solid rgba(255,255,255,0.15)",
    borderRadius: 8,
    fontSize: 16,
    fontWeight: 800,
    color: "#fff",
    letterSpacing: "-0.01em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    transition: "transform 0.12s, box-shadow 0.12s",
    marginBottom: 12,
  },
  formFootnote: {
    fontSize: 11,
    color: "#334155",
    textAlign: "center" as React.CSSProperties["textAlign"],
    letterSpacing: "0.01em",
  },

  /* ── Marquee ── */
  marqueeOuter: {
    position: "absolute",
    top: "12%",
    left: 0,
    right: 0,
    zIndex: 2,
    borderTop: "2px solid #000",
    borderBottom: "2px solid #000",
    background: "#fff",
    overflow: "hidden",
    padding: "14px 0",
  },
  marqueeTrack: {
    display: "flex",
    whiteSpace: "nowrap" as React.CSSProperties["whiteSpace"],
    animation: "marquee 36s linear infinite",
  },
  marqueeItem: {
    display: "inline-flex",
    alignItems: "center",
    gap: 10,
    padding: "0 20px",
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: "0.12em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#000",
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    whiteSpace: "nowrap" as React.CSSProperties["whiteSpace"],
  },
  marqueeDiamond: {
    fontSize: 7,
    color: "#2563eb",
    flexShrink: 0,
  },

  /* ── Shared section ── */
  sectionInner: {
    maxWidth: 1160,
    margin: "0 auto",
    padding: "0 48px",
  },
  sectionLabel: {
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: "0.16em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#3b82f6",
    marginBottom: 16,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  },
  sectionHeading: {
    fontSize: 44,
    fontWeight: 900,
    letterSpacing: "-0.035em",
    color: "#f1f5f9",
    margin: "0 0 52px 0",
    lineHeight: 1.08,
  },

  /* ── How It Works ── */
  howSection: {
    background: "rgba(1,6,18,0.9)",
    borderTop: "1px solid rgba(255,255,255,0.06)",
    padding: "100px 0",
  },
  stepsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 16,
  },
  stepCard: {
    position: "relative",
    overflow: "hidden",
    padding: "32px 28px 36px",
    background: "rgba(8,20,52,0.7)",
    border: "1.5px solid rgba(255,255,255,0.14)",
    borderRadius: 10,
    boxShadow: "4px 4px 0 rgba(255,255,255,0.05)",
  },
  stepNumGhost: {
    position: "absolute",
    top: -16,
    right: -4,
    fontSize: 130,
    fontWeight: 900,
    lineHeight: 1,
    letterSpacing: "-0.06em",
    color: "rgba(255,255,255,0.04)",
    userSelect: "none" as React.CSSProperties["userSelect"],
    pointerEvents: "none",
  },
  stepNumLabel: {
    position: "relative",
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: "0.12em",
    color: "#3b82f6",
    marginBottom: 18,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  },
  stepTitle: {
    position: "relative",
    fontSize: 17,
    fontWeight: 700,
    color: "#e2e8f0",
    marginBottom: 10,
    lineHeight: 1.3,
    letterSpacing: "-0.015em",
  },
  stepBody: {
    position: "relative",
    fontSize: 14,
    color: "#64748b",
    lineHeight: 1.7,
    margin: 0,
  },

  /* ── Feature Callouts ── */
  featureSection: {
    background: "rgba(0,0,0,0.35)",
    borderTop: "1px solid rgba(255,255,255,0.05)",
    padding: "100px 0",
  },
  featureGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 16,
  },
  featureCard: {
    padding: "32px 28px 36px",
    background: "rgba(6,14,34,0.8)",
    border: "1.5px solid rgba(255,255,255,0.12)",
    borderRadius: 10,
    boxShadow: "4px 4px 0 rgba(59,130,246,0.12)",
    display: "flex",
    flexDirection: "column" as React.CSSProperties["flexDirection"],
  },
  featureTag: {
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: "0.16em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#3b82f6",
    marginBottom: 16,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    borderBottom: "1px solid rgba(59,130,246,0.2)",
    paddingBottom: 12,
  },
  featureTitle: {
    fontSize: 17,
    fontWeight: 700,
    color: "#e2e8f0",
    marginBottom: 10,
    lineHeight: 1.3,
    letterSpacing: "-0.015em",
  },
  featureBody: {
    fontSize: 14,
    color: "#64748b",
    lineHeight: 1.7,
    margin: 0,
  },

  /* ── Bottom CTA ── */
  bottomCta: {
    background: "rgba(1,4,14,0.98)",
    borderTop: "2px solid rgba(255,255,255,0.08)",
    padding: "100px 48px",
    textAlign: "center" as React.CSSProperties["textAlign"],
  },
  bottomCtaInner: {
    maxWidth: 560,
    margin: "0 auto",
  },
  bottomCtaHeading: {
    fontSize: 54,
    fontWeight: 900,
    letterSpacing: "-0.04em",
    color: "#f1f5f9",
    margin: "0 0 16px 0",
    lineHeight: 1.05,
  },
  bottomCtaSubhead: {
    fontSize: 16,
    color: "#64748b",
    margin: "0 0 36px 0",
    lineHeight: 1.6,
  },
  ctaBottom: {
    display: "inline-block",
    padding: "14px 40px",
    background: "#2563eb",
    border: "2px solid rgba(255,255,255,0.2)",
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 800,
    color: "#fff",
    cursor: "pointer",
    letterSpacing: "-0.01em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    transition: "transform 0.12s, box-shadow 0.12s, background 0.12s",
  },

  /* ── Trust Bar ── */
  trustBar: {
    background: "rgba(0,0,0,0.5)",
    borderTop: "1px solid rgba(255,255,255,0.04)",
    padding: "20px 48px",
    textAlign: "center" as React.CSSProperties["textAlign"],
    fontSize: 12,
    color: "#334155",
    lineHeight: 1.65,
  },

  /* ── Footer ── */
  footer: {
    background: "rgba(0,0,0,0.65)",
    backdropFilter: "blur(8px)",
    borderTop: "1px solid rgba(255,255,255,0.05)",
    padding: "26px 48px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  footerWordmark: {
    fontSize: 14,
    fontWeight: 800,
    color: "#475569",
    letterSpacing: "-0.02em",
  },
  footerMeta: {
    fontSize: 12,
    color: "#334155",
  },
};
