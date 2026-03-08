import { useState } from "react";
import { startGeneration } from "../api/client";

interface Props {
  sessionId: string;
  onBack: () => void;
  onNext: (runId: string) => void;
}

export function JobDescriptionStep({ sessionId, onBack, onNext }: Props) {
  const [jd, setJd] = useState("");
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
      const res = await startGeneration(sessionId, jd);
      onNext(res.run_id);
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
        rows={18}
      />

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
    maxWidth: 640,
    margin: "0 auto",
    padding: "32px 40px",
    background: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 6 },
  subtitle: { color: "#555", marginBottom: 20 },
  textarea: {
    width: "100%",
    padding: "12px",
    border: "1px solid #ddd",
    borderRadius: 6,
    fontSize: 13,
    resize: "vertical",
    boxSizing: "border-box",
    marginBottom: 16,
    fontFamily: "inherit",
  },
  buttonRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  primary: {
    padding: "10px 28px",
    background: "#1a1a1a",
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
    color: "#333",
    border: "1px solid #ccc",
    borderRadius: 6,
    fontSize: 15,
    cursor: "pointer",
  },
  error: { color: "#c00", marginBottom: 12, fontSize: 14 },
};
