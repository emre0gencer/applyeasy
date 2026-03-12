import { useState } from "react";
import { startGeneration } from "../api/client";

interface TemplateOption {
  id: string;
  name: string;
  description: string;
  detail: string;
}

const TEMPLATES: TemplateOption[] = [
  {
    id: "classic",
    name: "Classic",
    description: "Centered · compact · all-caps headings",
    detail: "Safe for any role. Maximum content density.",
  },
  {
    id: "polished",
    name: "Polished",
    description: "Left-aligned · modern hierarchy · more space",
    detail: "Great for tech, product, and business roles.",
  },
  {
    id: "traditional",
    name: "Traditional",
    description: "Serif · centered · double-rule headings",
    detail: "Finance, law, consulting, and senior executive roles.",
  },
];

interface Props {
  sessionId: string;
  onBack: () => void;
  onNext: (runId: string, jd: string, includeCoverLetter: boolean) => void;
  initialJd?: string;
}

function TemplatePreview({ id, selected }: { id: string; selected: boolean }) {
  const fg = (op: number) =>
    selected ? `rgba(255,255,255,${Math.min(op + 0.22, 1)})` : `rgba(255,255,255,${op})`;

  const bar = (w: string, h: number, op = 0.28) => ({
    width: w,
    height: h,
    background: fg(op),
    borderRadius: 1,
    flexShrink: 0,
  });

  const base = {
    display: "flex" as const,
    flexDirection: "column" as const,
    gap: 3,
    width: "100%",
    padding: "16px 18px 14px",
  };

  if (id === "classic") {
    return (
      <div style={{ ...base, alignItems: "center" as const }}>
        <div style={bar("44%", 4, 0.5)} />
        <div style={bar("26%", 2, 0.3)} />
        <div style={{ ...bar("76%", 1, 0.1), marginTop: 5, marginBottom: 4 }} />
        <div style={bar("82%", 2, 0.25)} />
        <div style={bar("70%", 2, 0.25)} />
        <div style={bar("76%", 2, 0.25)} />
      </div>
    );
  }

  if (id === "polished") {
    return (
      <div style={{ ...base, alignItems: "flex-start" as const }}>
        <div style={bar("54%", 4, 0.5)} />
        <div style={bar("28%", 2, 0.3)} />
        <div
          style={{
            display: "flex" as const,
            gap: 6,
            marginTop: 6,
            width: "100%",
            alignItems: "stretch" as const,
          }}
        >
          <div
            style={{
              width: 2,
              background: fg(0.5),
              borderRadius: 1,
              alignSelf: "stretch" as const,
              flexShrink: 0,
            }}
          />
          <div
            style={{
              flex: 1,
              display: "flex" as const,
              flexDirection: "column" as const,
              gap: 3,
            }}
          >
            <div style={bar("90%", 2, 0.25)} />
            <div style={bar("76%", 2, 0.25)} />
            <div style={bar("83%", 2, 0.25)} />
          </div>
        </div>
      </div>
    );
  }

  // traditional
  return (
    <div style={{ ...base, alignItems: "center" as const }}>
      <div style={bar("40%", 4, 0.5)} />
      <div style={{ ...bar("68%", 1, 0.2), marginTop: 3 }} />
      <div style={{ ...bar("68%", 1, 0.1), marginBottom: 5 }} />
      <div style={bar("80%", 2, 0.25)} />
      <div style={bar("68%", 2, 0.25)} />
      <div style={bar("74%", 2, 0.25)} />
    </div>
  );
}

export function JobDescriptionStep({ sessionId, onBack, onNext, initialJd = "" }: Props) {
  const [jd, setJd] = useState(initialJd);
  const [templateId, setTemplateId] = useState("classic");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleGenerate() {
    if (!jd.trim()) {
      setError("Please paste a job description.");
      return;
    }
    if (jd.trim().length < 50) {
      setError("Job description is too short — paste the full posting.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await startGeneration(sessionId, jd, templateId, false);
      onNext(res.run_id, jd, false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start generation");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.cardTop}>
        <h2 style={styles.title}>Paste the job description</h2>
        <p style={styles.subtitle}>Use the complete posting for best keyword coverage.</p>
      </div>

      {/* Textarea — full-bleed */}
      <textarea
        style={styles.textarea}
        value={jd}
        onChange={(e) => setJd(e.target.value)}
        placeholder="Paste the complete job description here…"
        rows={13}
      />

      {/* Template selection */}
      <div style={styles.section}>
        <p style={styles.sectionLabel}>Resume template</p>
        <div style={styles.templateGrid} role="radiogroup">
          {TEMPLATES.map((t) => {
            const selected = templateId === t.id;
            return (
              <label
                key={t.id}
                style={{
                  ...styles.templateCard,
                  ...(selected ? styles.templateCardSelected : styles.templateCardUnselected),
                }}
              >
                <input
                  type="radio"
                  name="template"
                  value={t.id}
                  checked={selected}
                  onChange={() => setTemplateId(t.id)}
                  style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
                />
                {/* Mini layout preview */}
                <div
                  style={{
                    background: selected ? "rgba(59,130,246,0.07)" : "rgba(255,255,255,0.025)",
                    borderBottom: selected
                      ? "1px solid rgba(59,130,246,0.14)"
                      : "1px solid rgba(255,255,255,0.06)",
                  }}
                >
                  <TemplatePreview id={t.id} selected={selected} />
                </div>
                {/* Card text */}
                <div style={styles.cardBody}>
                  <div style={styles.cardNameRow}>
                    <span
                      style={{
                        ...styles.templateName,
                        color: selected ? "#f1f5f9" : "#cbd5e1",
                      }}
                    >
                      {t.name}
                    </span>
                    {selected && (
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
                        <circle cx="8" cy="8" r="7.5" fill="rgba(37,99,235,0.4)" stroke="#3b82f6" />
                        <path d="M5 8L7 10.5L11 5.5" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>
                  <span
                    style={{
                      ...styles.templateDesc,
                      color: selected ? "rgba(255,255,255,0.6)" : "#64748b",
                    }}
                  >
                    {t.description}
                  </span>
                  <span
                    style={{
                      ...styles.templateDetail,
                      color: selected ? "rgba(255,255,255,0.42)" : "#475569",
                    }}
                  >
                    {t.detail}
                  </span>
                </div>
              </label>
            );
          })}
        </div>
      </div>

      {/* Documents to generate */}
      <div style={styles.section}>
        <p style={styles.sectionLabel}>Documents to generate</p>
        <div style={styles.docRow}>
          {/* Resume — always on */}
          <div style={{ ...styles.docCard, ...styles.docCardActive }}>
            <div style={styles.docCardInner}>
              <span style={styles.docCheckMark}>✓</span>
              <div>
                <div style={styles.docTitle}>Resume</div>
                <div style={styles.docSub}>ATS-safe tailored PDF</div>
              </div>
            </div>
          </div>
          {/* Cover Letter — locked */}
          <div style={{ ...styles.docCard, ...styles.docCardLocked, position: "relative" }}>
            <span style={styles.proBadge}>PRO</span>
            <div style={styles.docCardInner}>
              <span style={styles.docLockMark}>✉</span>
              <div>
                <div style={styles.docTitleLocked}>Cover Letter</div>
                <div style={styles.docSub}>Grounded narrative</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {error && <p style={styles.error}>{error}</p>}

      <div style={styles.buttonRow}>
        <button style={styles.secondary} onClick={onBack} disabled={loading}>
          ← Back
        </button>
        <button style={styles.primary} onClick={handleGenerate} disabled={loading}>
          {loading ? "Starting…" : "Generate Resume →"}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 840,
    margin: "0 auto",
    background: "rgba(2,15,36,0.82)",
    backdropFilter: "blur(20px)",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,0.09)",
    boxShadow: "0 4px 6px -1px rgba(0,0,0,0.4), 0 24px 64px -12px rgba(0,0,0,0.55)",
    overflow: "hidden",
  },
  cardTop: {
    padding: "36px 44px 24px",
  },
  title: {
    fontSize: 24,
    fontWeight: 700,
    color: "#f1f5f9",
    letterSpacing: "-0.025em",
    margin: "0 0 6px 0",
  },
  subtitle: {
    color: "#64748b",
    fontSize: 14,
    margin: 0,
    lineHeight: 1.5,
  },
  textarea: {
    display: "block",
    width: "100%",
    padding: "18px 44px",
    borderTop: "1px solid rgba(255,255,255,0.07)",
    borderBottom: "1px solid rgba(255,255,255,0.07)",
    borderLeft: "none",
    borderRight: "none",
    fontSize: 14,
    resize: "vertical",
    boxSizing: "border-box",
    fontFamily: "inherit",
    background: "rgba(255,255,255,0.03)",
    color: "#e2e8f0",
    outline: "none",
    lineHeight: 1.65,
  },
  section: {
    padding: "28px 44px 0",
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#475569",
    margin: "0 0 12px 0",
  },
  templateGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 10,
  },
  templateCard: {
    position: "relative",
    display: "flex",
    flexDirection: "column",
    cursor: "pointer",
    borderRadius: 10,
    overflow: "hidden",
    transition: "border-color 0.12s, box-shadow 0.12s",
  },
  templateCardSelected: {
    border: "1.5px solid #3b82f6",
    boxShadow: "0 0 0 1px rgba(59,130,246,0.1), 0 4px 16px rgba(37,99,235,0.1)",
  },
  templateCardUnselected: {
    border: "1.5px solid rgba(255,255,255,0.08)",
  },
  cardBody: {
    padding: "10px 14px 14px",
    display: "flex",
    flexDirection: "column",
    gap: 3,
  },
  cardNameRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 3,
  },
  templateName: {
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "-0.01em",
  },
  templateDesc: {
    fontSize: 11,
    lineHeight: 1.4,
  },
  templateDetail: {
    fontSize: 11,
    lineHeight: 1.4,
    marginTop: 1,
  },
  docRow: {
    display: "flex",
    gap: 10,
  },
  docCard: {
    flex: 1,
    borderRadius: 8,
    padding: "12px 16px",
  },
  docCardActive: {
    background: "rgba(22,163,74,0.07)",
    border: "1.5px solid rgba(22,163,74,0.25)",
  },
  docCardLocked: {
    background: "rgba(255,255,255,0.025)",
    border: "1.5px solid rgba(255,255,255,0.07)",
    cursor: "not-allowed",
  },
  docCardInner: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  docCheckMark: {
    width: 26,
    height: 26,
    borderRadius: "50%",
    background: "rgba(22,163,74,0.15)",
    border: "1px solid rgba(22,163,74,0.35)",
    color: "#16a34a",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    fontWeight: 700,
    flexShrink: 0,
  },
  docLockMark: {
    width: 26,
    height: 26,
    borderRadius: "50%",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
    color: "#475569",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    flexShrink: 0,
  },
  docTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "#e2e8f0",
    lineHeight: 1,
    marginBottom: 3,
  },
  docTitleLocked: {
    fontSize: 13,
    fontWeight: 700,
    color: "#475569",
    lineHeight: 1,
    marginBottom: 3,
  },
  docSub: {
    fontSize: 11,
    color: "#475569",
    lineHeight: 1.3,
  },
  proBadge: {
    position: "absolute",
    top: 8,
    right: 8,
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: "0.08em",
    color: "#92400e",
    background: "linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)",
    border: "1px solid #f59e0b",
    padding: "2px 5px",
    borderRadius: 3,
  },
  error: {
    color: "#fca5a5",
    fontSize: 13,
    padding: "10px 44px 0",
    margin: 0,
  },
  buttonRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "24px 44px 36px",
    marginTop: 8,
  },
  primary: {
    padding: "12px 32px",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: "-0.01em",
  },
  secondary: {
    padding: "12px 24px",
    background: "transparent",
    color: "#64748b",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    fontSize: 15,
    cursor: "pointer",
  },
};
