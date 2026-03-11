import { useEffect, useRef, useState } from "react";
import { uploadText } from "../api/client";

interface Props {
  onSubmit: (sessionId: string, rawText: string) => void;
  initialText?: string;
}

export function LandingPage({ onSubmit, initialText = "" }: Props) {
  const [scrolled, setScrolled] = useState(false);
  const [text, setText] = useState(initialText);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [ctaHovered, setCtaHovered] = useState(false);
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
    textareaRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => textareaRef.current?.focus(), 400);
  }

  const navBg = scrolled ? "rgba(2,12,27,0.92)" : "transparent";
  const navBorder = scrolled ? "1px solid rgba(255,255,255,0.08)" : "1px solid transparent";
  const navBlur = scrolled ? "blur(12px)" : "none";

  return (
    <div style={s.root}>
      {/* ── Nav ── */}
      <nav
        style={{
          ...s.nav,
          background: navBg,
          backdropFilter: navBlur,
          borderBottom: navBorder,
        }}
      >
        <span style={s.navWordmark}>
          <span style={{ color: "#f1f5f9", fontWeight: 700 }}>Apply</span>
          <span style={{ color: "#60a5fa", fontWeight: 800 }}>Easy</span>
        </span>
        <a href="#how-it-works" style={s.navLink}>How it works</a>
      </nav>

      {/* ── Hero ── */}
      <section style={s.hero}>
        <div style={s.heroInner}>
          {/* Left — headline */}
          <div style={s.heroLeft}>
            <div style={s.eyebrow}>AI-powered · ATS-safe · Zero hallucination</div>
            <h1 style={s.headline}>
              Your resume,<br />rewritten for<br />every job.
            </h1>
            <p style={s.subhead}>
              Paste your background once. ApplyEasy reads the job description,
              selects what's relevant, and rewrites your bullets with the right
              keywords — grounded entirely in your real experience.
            </p>
            <div style={s.heroMeta}>
              <span style={s.metaPill}>✓ ATS-safe PDF</span>
              <span style={s.metaPill}>✓ One page by default</span>
              <span style={s.metaPill}>✓ ~30 seconds</span>
            </div>

            <div style={s.disclaimer}>
              <span style={s.disclaimerIcon}>⚠</span>
              <p style={s.disclaimerText}>
                <strong>Use at your own risk.</strong> This application is meant to provide the best version of your academic/professional profile in the context of the said job posting and the information you provide about yourself in a clear format. Application doesn't take into account that you might be lying, misrepresenting, or misclaiming your information; nor that you might be applying to a job clearly out of scope of your own profile; these are the obvious wrong usages of this application. Application isn't programmed to deliver reliable results in similar wide-ranging mis-use circumstances.
              </p>
            </div>
          </div>

          {/* Right — embedded form */}
          <div style={s.formCard}>
            <div style={s.formHeader}>
              <div style={s.formTitle}>Start here</div>
              <div style={s.formSubtitle}>
                Paste your resume, LinkedIn text, or anything professionally relevant.
                No formatting required.
              </div>
            </div>
            <textarea
              ref={textareaRef}
              style={{
                ...s.textarea,
                borderColor: textareaFocused ? "#6366f1" : error ? "#dc2626" : "rgba(255,255,255,0.12)",
                boxShadow: textareaFocused ? "0 0 0 3px rgba(99,102,241,0.2)" : "none",
              }}
              value={text}
              onChange={(e) => { setText(e.target.value); if (error) setError(""); }}
              onFocus={() => setTextareaFocused(true)}
              onBlur={() => setTextareaFocused(false)}
              placeholder={
                "Jane Smith\njane@email.com | linkedin.com/in/janesmith\n\nSoftware Engineer at Acme Corp (Jan 2022 – Present)\n- Built Kafka pipeline processing 2M events/day\n- Led migration from monolith to microservices\n\nB.S. Computer Science, UC Berkeley, 2020\nGPA: 3.8 | Dean's List\n\nSkills: Python, FastAPI, React, PostgreSQL, Docker, Kubernetes"
              }
              rows={12}
            />
            {error && <div style={s.errorMsg}>{error}</div>}
            <button
              style={{
                ...s.cta,
                background: loading ? "#818cf8" : ctaHovered ? "#4f46e5" : "#6366f1",
                transform: ctaHovered && !loading ? "translateY(-1px)" : "none",
                cursor: loading ? "not-allowed" : "pointer",
              }}
              onClick={handleSubmit}
              disabled={loading}
              onMouseEnter={() => setCtaHovered(true)}
              onMouseLeave={() => setCtaHovered(false)}
            >
              {loading ? "Processing…" : "Tailor my resume →"}
            </button>
            <div style={s.formFootnote}>
              No account required. Your data is never stored beyond your session.
            </div>
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section id="how-it-works" style={s.howSection}>
        <div style={s.sectionInner}>
          <div style={s.sectionEyebrow}>How it works</div>
          <h2 style={s.sectionHeading}>From raw resume to tailored PDF in three steps.</h2>
          <div style={s.stepsGrid}>
            {[
              {
                n: "1",
                title: "Paste your background",
                body: "Drop in your full work history, skills, and education. Any plain text works — resume, LinkedIn export, or freeform notes.",
              },
              {
                n: "2",
                title: "Add the job description",
                body: "Paste the full job posting. ApplyEasy extracts requirements, importance-ranked keywords, and what the role actually demands.",
              },
              {
                n: "3",
                title: "Download tailored documents",
                body: "Get a one-page ATS-safe PDF with reordered, keyword-rich bullets — every claim traceable to your real experience.",
              },
            ].map((step) => (
              <div key={step.n} style={s.stepCard}>
                <div style={s.stepNum}>{step.n}</div>
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
          <div style={s.sectionEyebrow}>Why it works</div>
          <h2 style={s.sectionHeading}>Built differently from other AI resume tools.</h2>
          <div style={s.featureGrid}>
            {[
              {
                icon: "⊙",
                title: "ATS-safe by design",
                body: "The output PDF uses a clean single-column layout with standard section headings that applicant tracking systems expect. No tables, no columns, no parsing failures.",
              },
              {
                icon: "⊘",
                title: "Zero hallucination guarantee",
                body: "Every rewritten bullet is grounded in your original text. A validation layer flags any metric, name, or claim that wasn't present in your source material.",
              },
              {
                icon: "◎",
                title: "Keyword-targeted, not keyword-stuffed",
                body: "Keywords are ranked by importance from the job description and woven in only where technically accurate. The engine caps integrations per bullet so copy reads naturally.",
              },
            ].map((f) => (
              <div key={f.title} style={s.featureCard}>
                <div style={s.featureIcon}>{f.icon}</div>
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
          <h2 style={s.bottomCtaHeading}>Ready to tailor your first application?</h2>
          <p style={s.bottomCtaSubhead}>No account. No credit card. Paste and go.</p>
          <button
            style={{
              ...s.cta,
              background: ctaHovered ? "#4f46e5" : "#6366f1",
              marginTop: 8,
            }}
            onClick={scrollToForm}
          >
            Get started →
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

const s: Record<string, React.CSSProperties> = {
  root: {
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    color: "#f1f5f9",
    background: "transparent",
    overflowX: "hidden",
  },

  /* Nav */
  nav: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 100,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "0 40px",
    height: 60,
    transition: "background 0.2s, box-shadow 0.2s, border-bottom 0.2s",
  },
  navWordmark: {
    fontSize: 20,
    letterSpacing: "-0.03em",
    display: "flex",
    alignItems: "baseline",
    gap: 0,
    userSelect: "none" as const,
  },
  navLink: {
    fontSize: 14,
    color: "#94a3b8",
    textDecoration: "none",
    fontWeight: 500,
  },

  /* Hero */
  hero: {
    minHeight: "100vh",
    paddingTop: 60,
    display: "flex",
    alignItems: "center",
    background: "transparent",
  },
  heroInner: {
    maxWidth: 1100,
    margin: "0 auto",
    padding: "80px 48px",
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "72px",
    alignItems: "center",
    width: "100%",
    boxSizing: "border-box",
  },
  heroLeft: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "#818cf8",
    marginBottom: 20,
  },
  headline: {
    fontSize: 56,
    fontWeight: 800,
    lineHeight: 1.05,
    letterSpacing: "-0.035em",
    color: "#f1f5f9",
    margin: "0 0 24px 0",
  },
  subhead: {
    fontSize: 18,
    lineHeight: 1.65,
    color: "#94a3b8",
    margin: "0 0 32px 0",
    maxWidth: 460,
  },
  heroMeta: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
  },
  metaPill: {
    fontSize: 13,
    fontWeight: 500,
    color: "#94a3b8",
    background: "rgba(255,255,255,0.06)",
    padding: "5px 12px",
    borderRadius: 100,
    border: "1px solid rgba(255,255,255,0.1)",
  },

  disclaimer: {
    marginTop: 16,
    display: "flex",
    alignItems: "flex-start",
    gap: 8,
    padding: "9px 12px",
    background: "rgba(127,29,29,0.25)",
    border: "1px solid rgba(127,29,29,0.5)",
    borderRadius: 7,
  },
  disclaimerIcon: {
    fontSize: 11,
    color: "#fca5a5",
    flexShrink: 0,
    marginTop: 1,
  },
  disclaimerText: {
    fontSize: 10,
    color: "#fca5a5",
    lineHeight: 1.55,
    margin: 0,
  },

  /* Form card */
  formCard: {
    background: "rgba(2,15,36,0.75)",
    backdropFilter: "blur(16px)",
    borderRadius: 16,
    padding: "32px",
    boxShadow: "0 4px 6px -1px rgba(0,0,0,0.4), 0 20px 60px -10px rgba(0,0,0,0.5)",
    border: "1px solid rgba(255,255,255,0.1)",
  },
  formHeader: {
    marginBottom: 16,
  },
  formTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "#f1f5f9",
    marginBottom: 4,
  },
  formSubtitle: {
    fontSize: 13,
    color: "#64748b",
    lineHeight: 1.55,
  },
  textarea: {
    width: "100%",
    padding: "12px 14px",
    border: "1.5px solid rgba(255,255,255,0.12)",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
    resize: "vertical",
    boxSizing: "border-box",
    marginBottom: 12,
    lineHeight: 1.6,
    color: "#cbd5e1",
    background: "rgba(255,255,255,0.05)",
    outline: "none",
    transition: "border-color 0.15s, box-shadow 0.15s",
    minHeight: 200,
  },
  errorMsg: {
    fontSize: 13,
    color: "#fca5a5",
    marginBottom: 10,
    marginTop: -6,
  },
  cta: {
    width: "100%",
    padding: "13px 24px",
    background: "#6366f1",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 700,
    cursor: "pointer",
    letterSpacing: "-0.01em",
    transition: "background 0.15s, transform 0.1s",
    marginBottom: 12,
  },
  formFootnote: {
    fontSize: 12,
    color: "#475569",
    textAlign: "center",
    lineHeight: 1.4,
  },

  /* How It Works */
  howSection: {
    background: "rgba(0,0,0,0.25)",
    padding: "96px 48px",
  },
  sectionInner: {
    maxWidth: 1000,
    margin: "0 auto",
  },
  sectionEyebrow: {
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "#818cf8",
    marginBottom: 12,
  },
  sectionHeading: {
    fontSize: 34,
    fontWeight: 800,
    letterSpacing: "-0.025em",
    color: "#f1f5f9",
    margin: "0 0 48px 0",
    lineHeight: 1.15,
  },
  stepsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 24,
  },
  stepCard: {
    padding: "28px",
    background: "rgba(255,255,255,0.04)",
    backdropFilter: "blur(8px)",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.08)",
  },
  stepNum: {
    width: 36,
    height: 36,
    background: "rgba(99,102,241,0.2)",
    color: "#818cf8",
    borderRadius: 8,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 15,
    fontWeight: 800,
    marginBottom: 16,
  },
  stepTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "#f1f5f9",
    marginBottom: 8,
  },
  stepBody: {
    fontSize: 14,
    color: "#94a3b8",
    lineHeight: 1.65,
  },

  /* Features */
  featureSection: {
    background: "transparent",
    padding: "96px 48px",
  },
  featureGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 24,
  },
  featureCard: {
    padding: "28px 24px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.08)",
    background: "rgba(255,255,255,0.03)",
    backdropFilter: "blur(8px)",
  },
  featureIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    background: "rgba(99,102,241,0.2)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
    fontSize: 20,
    color: "#818cf8",
  },
  featureTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "#f1f5f9",
    marginBottom: 8,
  },
  featureBody: {
    fontSize: 13,
    color: "#94a3b8",
    lineHeight: 1.65,
  },

  /* Bottom CTA */
  bottomCta: {
    background: "linear-gradient(135deg, rgba(99,102,241,0.9) 0%, rgba(79,70,229,0.9) 100%)",
    backdropFilter: "blur(8px)",
    padding: "80px 48px",
  },
  bottomCtaInner: {
    maxWidth: 600,
    margin: "0 auto",
    textAlign: "center",
  },
  bottomCtaHeading: {
    fontSize: 34,
    fontWeight: 800,
    letterSpacing: "-0.025em",
    color: "#fff",
    margin: "0 0 12px 0",
    lineHeight: 1.2,
  },
  bottomCtaSubhead: {
    fontSize: 16,
    color: "rgba(255,255,255,0.8)",
    margin: "0 0 8px 0",
  },

  /* Trust bar */
  trustBar: {
    background: "rgba(0,0,0,0.3)",
    padding: "20px 48px",
    textAlign: "center",
    fontSize: 13,
    color: "#475569",
    lineHeight: 1.6,
    borderTop: "1px solid rgba(255,255,255,0.06)",
  },

  /* Footer */
  footer: {
    background: "rgba(0,0,0,0.5)",
    backdropFilter: "blur(8px)",
    padding: "28px 48px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderTop: "1px solid rgba(255,255,255,0.06)",
  },
  footerWordmark: {
    fontSize: 16,
    fontWeight: 700,
    color: "#f1f5f9",
    letterSpacing: "-0.02em",
  },
  footerMeta: {
    fontSize: 13,
    color: "#475569",
  },
};
