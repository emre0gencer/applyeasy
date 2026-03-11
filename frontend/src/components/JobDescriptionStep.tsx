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
      <h2 style={styles.title}>Step 2 of 4: Job Description</h2>
      <p style={styles.subtitle}>Paste the full job posting below.</p>

      <textarea
        style={styles.textarea}
        value={jd}
        onChange={(e) => setJd(e.target.value)}
        placeholder="Paste the complete job description here..."
        rows={12}
      />

      <div style={styles.templateSection}>
        <p style={styles.templateLabel}>Resume template</p>
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
                <div style={styles.templateCardTop}>
                  <span style={{ ...styles.templateName, color: selected ? "#fff" : "#cbd5e1" }}>{t.name}</span>
                  {selected && <span style={styles.templateCheck}>✓</span>}
                </div>
                <span style={{ ...styles.templateDesc, color: selected ? "rgba(255,255,255,0.85)" : "#555" }}>{t.description}</span>
                <span style={{ ...styles.templateDetail, color: selected ? "rgba(255,255,255,0.65)" : "#888" }}>{t.detail}</span>
              </label>
            );
          })}
        </div>
      </div>

      <div style={styles.docSection}>
        <p style={styles.templateLabel}>Documents to generate</p>
        <div style={styles.docRow}>
          {/* Resume — always selected, always active */}
          <button
            type="button"
            onClick={() => {}}
            style={{ ...styles.docCard, ...styles.docCardSelected, position: "relative", cursor: "default" }}
          >
            <div style={styles.docCardTop}>
              <span style={{ ...styles.docIcon, color: "#15803d" }}>📄</span>
              <span style={{ ...styles.docCheck, opacity: 1 }}>✓</span>
            </div>
            <span style={{ ...styles.docLabel, color: "#14532d" }}>Resume</span>
            <span style={{ ...styles.docSub, color: "#16a34a" }}>ATS-safe tailored PDF</span>
          </button>

          {/* Cover Letter — locked PRO, never clickable */}
          <div style={{ ...styles.docCard, ...styles.docCardLocked, position: "relative" }}>
            <span style={styles.docProBadge}>🔒 PRO</span>
            <div style={styles.docCardTop}>
              <span style={{ ...styles.docIcon, color: "#475569" }}>✉</span>
            </div>
            <span style={{ ...styles.docLabel, color: "#94a3b8" }}>Cover Letter</span>
            <span style={{ ...styles.docSub, color: "#64748b" }}>Grounded narrative</span>
          </div>
        </div>
      </div>

      {error && <p style={styles.error}>{error}</p>}

      <div style={styles.buttonRow}>
        <button style={styles.secondary} onClick={onBack} disabled={loading}>
          ← Back
        </button>
        <button style={styles.primary} onClick={handleGenerate} disabled={loading}>
          {loading ? "Starting..." : "Generate Documents →"}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 680,
    margin: "0 auto",
    padding: "32px 40px",
    background: "rgba(2,15,36,0.8)",
    backdropFilter: "blur(16px)",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.1)",
    boxShadow: "0 4px 6px -1px rgba(0,0,0,0.4), 0 20px 60px -10px rgba(0,0,0,0.5)",
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 6, color: "#f1f5f9" },
  subtitle: { color: "#94a3b8", marginBottom: 20 },
  textarea: {
    width: "100%",
    padding: "12px",
    border: "1.5px solid rgba(255,255,255,0.12)",
    borderRadius: 6,
    fontSize: 13,
    resize: "vertical",
    boxSizing: "border-box",
    marginBottom: 20,
    fontFamily: "inherit",
    background: "rgba(255,255,255,0.05)",
    color: "#e2e8f0",
    outline: "none",
  },
  templateSection: {
    marginBottom: 20,
  },
  templateLabel: {
    fontSize: 13,
    fontWeight: 600,
    color: "#94a3b8",
    marginBottom: 10,
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
    alignItems: "flex-start",
    gap: 4,
    padding: "12px 14px",
    borderRadius: 6,
    cursor: "pointer",
    textAlign: "left",
    transition: "border-color 0.15s, background 0.15s",
  },
  templateCardSelected: {
    background: "#2563eb",
    border: "1.5px solid #3b82f6",
  },
  templateCardUnselected: {
    background: "rgba(255,255,255,0.04)",
    border: "1.5px solid rgba(255,255,255,0.1)",
    opacity: 0.75,
  },
  templateCardTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
  },
  templateCheck: {
    fontSize: 12,
    color: "#fff",
    fontWeight: 700,
  },
  templateName: {
    fontSize: 14,
    fontWeight: 700,
  },
  templateDesc: {
    fontSize: 11,
    lineHeight: 1.4,
  },
  templateDetail: {
    fontSize: 11,
    lineHeight: 1.4,
  },
  buttonRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  primary: {
    padding: "10px 28px",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    fontSize: 15,
    cursor: "pointer",
    fontWeight: 600,
  },
  secondary: {
    padding: "10px 24px",
    background: "transparent",
    color: "#94a3b8",
    border: "1px solid rgba(255,255,255,0.15)",
    borderRadius: 6,
    fontSize: 15,
    cursor: "pointer",
  },
  error: { color: "#fca5a5", marginBottom: 12, fontSize: 14 },

  docSection: {
    marginBottom: 20,
  },
  docRow: {
    display: "flex",
    gap: 10,
  },
  docCard: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    gap: 3,
    padding: "12px 14px",
    borderRadius: 8,
    cursor: "pointer",
    textAlign: "left",
    transition: "border-color 0.15s, background 0.15s",
    fontFamily: "inherit",
  },
  docCardSelected: {
    background: "rgba(22,163,74,0.12)",
    border: "1.5px solid rgba(22,163,74,0.5)",
    boxShadow: "0 0 0 3px rgba(22,163,74,0.08)",
  },
  docCardUnselected: {
    background: "rgba(255,255,255,0.04)",
    border: "1.5px solid rgba(255,255,255,0.1)",
  },
  docCardLocked: {
    background: "rgba(255,255,255,0.03)",
    border: "1.5px solid rgba(255,255,255,0.08)",
    cursor: "not-allowed",
  },
  docCardTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    marginBottom: 2,
  },
  docIcon: {
    fontSize: 18,
    lineHeight: 1,
  },
  docCheck: {
    fontSize: 12,
    fontWeight: 700,
    color: "#16a34a",
    transition: "opacity 0.1s",
  },
  docLabel: {
    fontSize: 14,
    fontWeight: 700,
    lineHeight: 1,
  },
  docSub: {
    fontSize: 11,
    lineHeight: 1.4,
  },
  docProBadge: {
    position: "absolute",
    top: 8,
    right: 8,
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: "0.06em",
    color: "#92400e",
    background: "linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)",
    border: "1px solid #f59e0b",
    padding: "2px 5px",
    borderRadius: 4,
  },
};
